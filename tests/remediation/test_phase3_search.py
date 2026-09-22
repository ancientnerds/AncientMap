"""The search lane (block A3): search records, the quota gate, the search stage, the evidence it adds,
the rerun plan and its prepared batches, the budget dry run, the CLI and the mass driver's part.

Nothing here opens a socket or starts a process: the search goes through a scripted `Searcher` (or a
real `MiniMaxSearcher` over `httpx.MockTransport`), the quota probe is a dict, and the clock is a
fixed instant. The interesting failures are silent ones - a missing quota field that lets a run
start, a search failure that reads like "no hits", a query that carries the value under test, a
rerun that quietly re-asks all five fields, an unwritten row that falls out of the plan - and each
has a test that goes red when its guard is removed.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import sys
import types
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest

REPO = Path(__file__).resolve().parents[2]
PHASE3_PARENT = REPO / "scripts" / "remediation"
if str(PHASE3_PARENT) not in sys.path:
    sys.path.insert(0, str(PHASE3_PARENT))

from phase3 import discover_stage as DS  # noqa: E402
from phase3 import fetch_stage as F  # noqa: E402
from phase3 import ledger as L  # noqa: E402
from phase3 import mass_run as MR  # noqa: E402
from phase3 import model_stage as MS  # noqa: E402
from phase3 import review_stage as RS  # noqa: E402
from phase3 import run as R  # noqa: E402
from phase3 import search_evidence as SE  # noqa: E402
from phase3 import search_plan as SPL  # noqa: E402
from phase3 import search_stage as SS  # noqa: E402
from phase3 import snapshot_plan as SP  # noqa: E402

from pipeline.lyra import minimax_shared as MX  # noqa: E402

TUESDAY = datetime(2026, 9, 22, 12, 0, tzinfo=UTC)  # 4.5 days before the reset: outside the window
FRIDAY = datetime(2026, 9, 25, 12, 0, tzinfo=UTC)  # 2.5 days before the reset: Theo's window
PROBE_OK = {
    "ok": True,
    "five_hour_remaining_percent": 98,
    "weekly_remaining_percent": 86,
    "weekly_remains_tokens": 500_000_000,
    "five_hour_remains_tokens": 90_000_000,
}
ENDPOINT = "https://api.minimax.io/v1/coding_plan/search"


# ── helpers ───────────────────────────────────────────────────────────────────────────────────────


def _site(
    site_id: str = "site-1",
    *,
    name: str = "Cave 1",
    values: dict[str, Any] | None = None,
    rerun: list[str] | None = None,
    qid: str | None = None,
    production: dict[str, Any] | None = None,
    unwritten: dict[str, dict[str, str]] | None = None,
) -> dict[str, Any]:
    """A discover record (one finding per field). With `rerun`, a search-plan record: its
    `rerun_fields`, the proposals the mass lane did not write (`unwritten`, default none) and the
    values a query reads (production's; default: the stored ones, changed by `production`)."""
    actual: dict[str, Any] = {
        "description": "A cave with paintings.",
        "period_start": -3000,
        "site_type": "Cave Structures",
        "country": "Spain",
        "card_description": "A painted cave.",
    }
    actual.update(values or {})
    record: dict[str, Any] = {
        "findings": [SP.finding_row(field, actual[field]) for field in SP.DISCOVER_FIELDS],
        "name": name,
        "site_id": site_id,
    }
    if qid:
        record["wikidata_qid"] = qid
    if rerun is not None:
        record["rerun_fields"] = rerun
        record["rerun_unwritten"] = dict(unwritten or {})
        record["query_values"] = {
            slot: (production or {}).get(slot, actual[slot]) for slot in SS.SLOT_FIELDS
        }
    return record


def _current_of(source: Path) -> dict[str, dict[str, Any]]:
    """Production's values for every site of a source run, equal to what the snapshot stores."""
    current: dict[str, dict[str, Any]] = {}
    for path in sorted(source.glob("batch-*/input.json")):
        for site in json.loads(path.read_text(encoding="utf-8"))["sites"]:
            current[site["site_id"]] = {
                name: DS.field_finding(site, name)["current_value"]
                for name in SPL.CURRENT_VALUE_FIELDS
            }
    return current


def _plan(source: Path, scope: str = "writable", prefix: str = "srch", **kwargs: Any) -> Any:
    """`build_search_plan` over a source run whose production values equal the snapshot's."""
    kwargs.setdefault("current", _current_of(source))
    return SPL.build_search_plan(source_run_dir=source, scope=scope, prefix=prefix, **kwargs)


def _batch(*sites: dict[str, Any], batch_id: str = "srch-0001") -> dict[str, Any]:
    return {"batch_id": batch_id, "ordinal": 1, "pass": R.DISCOVER_PASS, "sites": list(sites)}


def _enwiki(store: F.EvidenceStore, site_id: str, text: str = "Cave 1 is a cave.") -> None:
    path = store.path_for(site_id, F.FEATURE_ENWIKI)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _hit(rank: int, url: str, *, title: str = "T", snippet: str = "S", date: str = "") -> Any:
    return SE.StoredHit(rank=rank, title=title, url=url, snippet=snippet, date=date)


def _store_search(
    store: F.EvidenceStore, site_id: str, key: str, *hits: SE.StoredHit, query: str = "q"
) -> None:
    record = SE.SearchRecord(query=query, hits=tuple(hits), linkless=0)
    store.write(site_id=site_id, feature=SE.search_feature(key), body=record.to_bytes())


def _response(query: str, *items: tuple[str, str, str, str]) -> MX.SearchResponse:
    return MX.SearchResponse(
        query=query,
        items=tuple(MX.WebSearchResult(title=t, url=u, snippet=s, date=d) for t, u, s, d in items),
        http_status=200,
        body_bytes=123,
    )


class ScriptedSearcher:
    """The seam: each call takes the next scripted outcome (a response, or an error to raise)."""

    endpoint = ENDPOINT

    def __init__(self, *script: Any) -> None:
        self.script = list(script)
        self.queries: list[str] = []

    def search(self, query: str) -> MX.SearchResponse:
        self.queries.append(query)
        outcome = (
            self.script.pop(0)
            if self.script
            else _response(query, ("t", "https://e.org/x", "s", ""))
        )
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def _run_search(
    tmp_path: Path,
    batch: dict[str, Any],
    searcher: Any,
    *,
    probe: dict[str, Any] | None = None,
    now: datetime = TUESDAY,
) -> tuple[SS.SearchReport, F.EvidenceStore, Path, list[float], list[int]]:
    store = F.EvidenceStore(tmp_path / "evidence")
    ledger_path = tmp_path / "LEDGER.jsonl"
    slept: list[float] = []
    waits: list[int] = []
    report = SS.search_batch(
        batch=batch,
        searcher=searcher,
        store=store,
        ledger=L.Ledger(ledger_path),
        probe=lambda: dict(PROBE_OK if probe is None else probe),
        now=lambda: now,
        wait=lambda: waits.append(1),
        sleep=slept.append,
    )
    return report, store, ledger_path, slept, waits


def _lines(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


# ── search_evidence: which searches a site buys, and the stored record ───────────────────────────


def test_a_record_without_rerun_fields_buys_no_search_and_asks_all_fields() -> None:
    assert SE.rerun_fields(_site()) is None
    assert SE.search_slots(_site()) == ()


@pytest.mark.parametrize("value", [None, [], "period_start", ["period"], ["country", "country"]])
def test_a_damaged_rerun_fields_value_raises_and_never_widens_to_all_fields(value: Any) -> None:
    site = _site()
    site["rerun_fields"] = value
    with pytest.raises(R.InputError):
        SE.rerun_fields(site)


def test_rerun_fields_come_back_in_plan_order_and_the_two_texts_share_one_search() -> None:
    site = _site(rerun=["card_description", "country", "description", "period_start"])
    assert SE.rerun_fields(site) == ("description", "period_start", "country", "card_description")
    slots = SE.search_slots(site)
    assert [(s.key, s.fields) for s in slots] == [
        ("text", ("description", "card_description")),
        ("period_start", ("period_start",)),
        ("country", ("country",)),
    ]
    assert slots[0].feature == "minimax_search.text"
    assert set(SE.SEARCH_KEY_FOR_FIELD) == set(SP.DISCOVER_FIELDS)


def test_a_stored_record_round_trips_byte_identically(tmp_path: Path) -> None:
    record = SE.SearchRecord(
        query='"Cave 1" Spain', hits=(_hit(1, "https://e.org/a", date="2020"),), linkless=2
    )
    path = tmp_path / "r.txt"
    path.write_bytes(record.to_bytes())
    assert SE.read_record(path) == record
    assert SE.read_record(path).to_bytes() == record.to_bytes()
    assert b"\r" not in record.to_bytes() and record.to_bytes().endswith(b"\n")


@pytest.mark.parametrize(
    "payload",
    [
        {"hits": [], "linkless": 0, "query": "q", "at": "2026"},
        {"hits": [], "linkless": -1, "query": "q"},
        {"hits": [], "linkless": 0, "query": " "},
        {"hits": [{"date": "", "rank": 1, "snippet": "", "title": "", "url": ""}], "linkless": 0, "query": "q"},
        {"hits": [{"date": "", "rank": 2, "snippet": "", "title": "", "url": "https://a"}, {"date": "", "rank": 1, "snippet": "", "title": "", "url": "https://b"}], "linkless": 0, "query": "q"},
        {"hits": [{"date": None, "rank": 1, "snippet": "", "title": "", "url": "https://a"}], "linkless": 0, "query": "q"},
    ],
)  # fmt: skip
def test_a_record_this_module_would_not_write_is_refused(tmp_path: Path, payload: Any) -> None:
    path = tmp_path / "r.txt"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(R.InputError):
        SE.read_record(path)


def test_a_hit_is_plain_title_and_snippet_with_its_date() -> None:
    assert SE.hit_text(_hit(1, "https://a", title="Byllis", snippet="A city.", date="2021")) == (
        "Byllis\nA city. (2021)"
    )
    assert SE.hit_text(_hit(1, "https://a", title="", snippet="Only this.")) == "Only this."


@pytest.mark.parametrize(
    ("url", "excluded"),
    [
        ("https://ancientnerds.com/sites/es/cave-1", True),
        ("https://www.ancientnerds.com/x", True),
        ("https://old.reddit.com/r/x", True),
        ("https://www.tripadvisor.com/x", True),
        ("https://linux.com/x", False),  # `x.com` is blocked; a substring match would refuse this
        ("https://en.wikipedia.org/wiki/Cave", False),
        ("ftp://example.org/x", True),
        ("https:///no-host", True),
    ],
)
def test_own_and_blocked_hosts_are_excluded_by_host_never_by_substring(
    url: str, excluded: bool
) -> None:
    assert (SE.excluded_because(url) is not None) is excluded


# ── queries ───────────────────────────────────────────────────────────────────────────────────────


def _queries(site: dict[str, Any]) -> dict[str, str]:
    return {slot.key: SS.build_query(site, slot) for slot in SE.search_slots(site)}


@pytest.mark.parametrize(
    ("rerun", "key", "query"),
    [
        (["description", "card_description"], "text", '"Muzey Tanais" Spain Cave Structures'),
        (["period_start"], "period_start", '"Muzey Tanais" Spain archaeological site date century BC built'),
        (["site_type"], "site_type", '"Muzey Tanais" Spain archaeological site'),
        (["country"], "country", '"Muzey Tanais" Cave Structures archaeological site location'),
    ],
)  # fmt: skip
def test_each_query_uses_the_name_and_the_fields_the_site_does_not_rerun(
    rerun: list[str], key: str, query: str
) -> None:
    assert _queries(_site(name='Muzey "Tanais"', rerun=rerun)) == {key: query}


def test_no_query_of_a_site_carries_the_value_of_any_field_it_reruns() -> None:
    """Every search of a site feeds the one evidence set all its rerun fields are judged on.

    A period query that named the stored country would put country-confirming hits in front of the
    country question; so a slot whose field is rerun anywhere at the site is left out of every query.
    """
    site = _site(name="Akdam", rerun=list(SP.DISCOVER_FIELDS))
    assert _queries(site) == {
        "text": '"Akdam"',
        "period_start": '"Akdam" archaeological site date century BC built',
        "site_type": '"Akdam" archaeological site',
        "country": '"Akdam" archaeological site location',
    }
    for rerun in (
        ["country", "period_start"],
        ["country", "site_type"],
        ["site_type", "description"],
    ):
        queries = _queries(_site(name="Akdam", rerun=rerun))
        for asked in rerun:
            stored = str(DS.field_finding(_site(), asked)["current_value"])
            assert all(stored not in query for query in queries.values()), (rerun, queries)


def test_a_query_reads_productions_values_never_the_older_snapshot() -> None:
    """`Tempio di Zeus, Selinunte`: the snapshot says Greece, production was corrected to Italy."""
    site = _site(
        values={"country": "Greece"}, production={"country": "Italy"}, rerun=["period_start"]
    )
    assert _queries(site) == {
        "period_start": '"Cave 1" Italy archaeological site date century BC built'
    }
    del site["query_values"]
    with pytest.raises(R.InputError, match="query_values"):
        _queries(site)
    site["query_values"] = {"country": "Italy"}
    with pytest.raises(R.InputError, match="query_values"):
        _queries(site)


def test_a_name_ending_in_the_value_under_test_loses_it_and_one_that_carries_it_is_counted() -> (
    None
):
    stina = _site(name="Stina, Ukraine", values={"country": "Ukraine"}, rerun=["country"])
    assert _queries(stina) == {"country": '"Stina" Cave Structures archaeological site location'}
    assert SS.carried_by_queries(stina) == ()
    # Not under test, so the name stays whole.
    kept = _site(name="Stina, Ukraine", values={"country": "Ukraine"}, rerun=["period_start"])
    assert SS.query_name(kept) == "Stina, Ukraine" and SS.carried_by_queries(kept) == ()
    runes = _site(name="Runestones of Sweden", values={"country": "Sweden"}, rerun=["country"])
    assert SS.query_name(runes) == "Runestones of Sweden"
    assert SS.carried_by_queries(runes) == ("country",)
    dolmen = _site(name="Dolmen of Chianca", values={"site_type": "Dolmen"}, rerun=["site_type"])
    assert SS.carried_by_queries(dolmen) == ("site_type",)
    # A whole word, not a substring: "Spain" is not carried by "Hispania".
    assert SS.carried_by_queries(_site(name="Hispania Nova", rerun=["country"])) == ()
    # The template's own wording can carry a generic stored type; counted, like a name.
    generic = _site(values={"site_type": "Archaeological site"}, rerun=["site_type"])
    (query,) = _queries(generic).values()
    assert SS.query_carries(generic, query) == ("site_type",)


def test_a_site_without_a_name_cannot_be_searched() -> None:
    for name in ("", '""', "Spain, Spain"):
        site = _site(name=name, values={"country": "Spain"}, rerun=["country"])
        if name == "Spain, Spain":
            assert SS.query_name(site) == "Spain"  # only a trailing suffix is taken off
            continue
        with pytest.raises(R.InputError, match="there is none"):
            SS.build_query(site, SE.search_slots(site)[0])


def test_a_template_that_reads_a_field_it_is_asked_about_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(SS.QUERY_SLOTS, "country", ("site_type", "country"))
    monkeypatch.setitem(
        SS.QUERY_TEMPLATES, "country", '"{name}" {site_type} {country} archaeological site'
    )
    with pytest.raises(R.InputError, match="a field it is asked about"):
        SS._check_templates()


def test_a_template_that_names_a_field_it_does_not_declare_or_a_key_without_one_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(
        SS.QUERY_TEMPLATES, "country", '"{name}" {period_start} archaeological site'
    )
    with pytest.raises(R.InputError, match="template names"):
        SS._check_templates()
    monkeypatch.setitem(SS.QUERY_TEMPLATES, "country", '"{name}" {site_type} location')
    monkeypatch.setitem(SS.QUERY_SLOTS, "extra", ())
    monkeypatch.setitem(SS.QUERY_TEMPLATES, "extra", '"{name}"')
    with pytest.raises(R.InputError, match="exactly one query template"):
        SS._check_templates()


def test_a_slot_value_that_contains_the_value_under_test_is_refused() -> None:
    site = _site(values={"country": "Chile", "site_type": "Chile rock art"}, rerun=["country"])
    (slot,) = SE.search_slots(site)
    with pytest.raises(R.InputError, match="value under test"):
        SS.build_query(site, slot)


def test_a_slot_value_that_contains_another_rerun_fields_value_is_refused_in_every_query() -> None:
    """The period query does not serve `site_type`, but its hits reach the site-type question."""
    site = _site(
        values={"country": "Temple Mount", "site_type": "Temple"},
        rerun=["period_start", "site_type"],
    )
    period = next(slot for slot in SE.search_slots(site) if slot.key == "period_start")
    with pytest.raises(R.InputError, match="value under test"):
        SS.build_query(site, period)


def test_an_empty_slot_is_left_out_rather_than_guessed() -> None:
    site = _site(values={"country": None}, rerun=["site_type"])
    (slot,) = SE.search_slots(site)
    assert SS.build_query(site, slot) == '"Cave 1" archaeological site'


# ── the quota gate ────────────────────────────────────────────────────────────────────────────────


def test_a_healthy_probe_outside_theos_window_lets_the_search_run() -> None:
    assert SS.quota_stop_reason(PROBE_OK, now_utc=TUESDAY) is None


@pytest.mark.parametrize(
    ("change", "match"),
    [
        ({"ok": False, "error": "http_401"}, "did not answer"),
        ({"ok": None}, "did not answer"),
        ({"ok": "true"}, "did not answer"),
        ({"weekly_remaining_percent": None}, "weekly_remaining_percent"),
        ({"five_hour_remaining_percent": "90"}, "five_hour_remaining_percent"),
        ({"weekly_remains_tokens": True}, "weekly_remains_tokens"),
        ({"weekly_remaining_percent": 25}, "weekly quota at 25%"),
        ({"five_hour_remaining_percent": 20}, "5h quota at 20%"),
    ],
)
def test_the_gate_fails_closed(change: dict[str, Any], match: str) -> None:
    probe = {**PROBE_OK, **change}
    assert SS.quota_stop_reason(probe, now_utc=TUESDAY) is not None
    assert match in str(SS.quota_stop_reason(probe, now_utc=TUESDAY))


@pytest.mark.parametrize("field", SS.QUOTA_FIELDS)
def test_a_missing_quota_field_never_satisfies_the_gate(field: str) -> None:
    probe = {k: v for k, v in PROBE_OK.items() if k != field}
    assert field in str(SS.quota_stop_reason(probe, now_utc=TUESDAY))


def test_the_gate_refuses_to_start_inside_theos_batch_window() -> None:
    assert "Theo's batch window" in str(SS.quota_stop_reason(PROBE_OK, now_utc=FRIDAY))


def test_the_floors_and_the_window_are_the_prospectors_and_theos_own() -> None:
    """Copied because importing their modules opens the database layer or builds the app."""
    from api.services import theo_config
    from pipeline.lyra import prospector

    assert SS.QUOTA_WEEKLY_FLOOR_PCT == prospector.QUOTA_WEEKLY_FLOOR_PCT
    assert SS.QUOTA_FIVE_HOUR_FLOOR_PCT == prospector.QUOTA_FIVE_HOUR_FLOOR_PCT
    assert SS.THEO_BATCH_MAX_DAYS_TO_RESET == theo_config.THEO_BATCH_MAX_DAYS_TO_RESET
    assert SS.QUOTA_WEEKLY_FLOOR_PCT > theo_config.QUOTA_WEEKLY_FREEZE_PCT


# ── the search stage ──────────────────────────────────────────────────────────────────────────────


def test_a_search_stores_one_record_and_writes_one_ledger_line(tmp_path: Path) -> None:
    site = _site(rerun=["period_start"])
    searcher = ScriptedSearcher(
        _response(
            "q",
            ("Cave 1", "https://e.org/a", "Painted in 3000 BC.", "2020"),
            ("Ours", "https://ancientnerds.com/x", "our value", ""),
            ("Nothing", "", "", ""),
        )
    )
    report, store, ledger, _, waits = _run_search(tmp_path, _batch(site), searcher)
    assert report.stopped is None and not report.failed
    (outcome,) = report.outcomes
    assert (outcome.stored, outcome.hits, outcome.linkless, outcome.excluded) == (True, 2, 1, 1)
    record = SE.read_record(store.path_for("site-1", "minimax_search.period_start"))
    assert [hit.url for hit in record.hits] == ["https://e.org/a", "https://ancientnerds.com/x"]
    assert record.query == searcher.queries[0]
    (line,) = _lines(ledger)
    assert line["kind"] == "fetch" and line["outcome"] == "ok" and line["http_status"] == 200
    assert line["label"] == "site-1/minimax_search.period_start"
    assert line["url"].startswith(ENDPOINT + "?q=%22Cave%201%22")
    assert waits == [1]  # the pace is asked before the request
    assert report.quota_before["weekly_remains_tokens"] == PROBE_OK["weekly_remains_tokens"]
    assert report.quota_after["ok"] is True


def test_an_existing_search_is_never_bought_again(tmp_path: Path) -> None:
    site = _site(rerun=["period_start", "site_type"])
    _run_search(tmp_path, _batch(site), ScriptedSearcher())
    before = _lines(tmp_path / "LEDGER.jsonl")
    again = ScriptedSearcher()
    report, *_ = _run_search(tmp_path, _batch(site), again)
    assert again.queries == []
    assert _lines(tmp_path / "LEDGER.jsonl") == before
    assert all(o.existing and o.failure is None for o in report.outcomes)


def test_a_stored_search_is_reused_only_for_the_query_it_answered(tmp_path: Path) -> None:
    """A template or a query value changed after the pilot must not reuse the old hits silently."""
    site = _site(rerun=["period_start"])
    _run_search(
        tmp_path, _batch(site), ScriptedSearcher(_response("q", ("t", "https://e.org/a", "s", "")))
    )
    again, *_ = _run_search(tmp_path, _batch(site), ScriptedSearcher())
    (outcome,) = again.outcomes
    assert outcome.existing and (outcome.hits, outcome.stored) == (1, False)  # read, not re-bought
    moved = _site(rerun=["period_start"], production={"country": "Portugal"})
    with pytest.raises(R.InputError, match="changed query needs a new run directory"):
        _run_search(tmp_path, _batch(moved), ScriptedSearcher())


def test_a_resumed_batch_keeps_what_its_first_run_measured(tmp_path: Path) -> None:
    """The first run's readings are the plan's only cost signal; a resume must not null them."""
    site_a, site_b = _site("site-1", rerun=["country"]), _site("site-2", rerun=["country"])
    first = {**PROBE_OK, "weekly_remains_tokens": 1000}
    report, *_ = _run_search(
        tmp_path,
        _batch(site_a, site_b),
        ScriptedSearcher(_response("q"), *[MX.CodingPlanTransportError("reset")] * F.MAX_ATTEMPTS),
        probe=first,
    )
    path = tmp_path / "search.json"
    SS.write_report(path, report)
    assert [entry["requests"] for entry in SS.read_quota(path)] == [1 + F.MAX_ATTEMPTS]
    second, *_ = _run_search(tmp_path, _batch(site_a, site_b), ScriptedSearcher(), probe=PROBE_OK)
    assert second.quota_before is not None  # site-2 was still pending, so this run probed
    second.earlier_quota = SS.read_quota(path)
    SS.write_report(path, second)
    third, *_ = _run_search(
        tmp_path, _batch(site_a, site_b), ScriptedSearcher(), probe={"ok": False}
    )
    third.earlier_quota = SS.read_quota(path)
    SS.write_report(path, third)  # nothing pending: no probe, no entry, the history stays
    readings = SS.read_quota(path)
    assert [entry["before"]["weekly_remains_tokens"] for entry in readings] == [1000, 500_000_000]
    assert [entry["requests"] for entry in readings] == [1 + F.MAX_ATTEMPTS, 1]
    totals = json.loads(path.read_text(encoding="utf-8"))["totals"]
    assert (totals["existing"], totals["requests"], totals["failed"]) == (2, 0, 0)


@pytest.mark.parametrize(
    "payload",
    [
        "{",
        json.dumps({"quota": {"before": {}, "after": {}}}),
        json.dumps({"quota": [{"before": {}}]}),
    ],
)
def test_a_damaged_quota_history_raises_instead_of_being_dropped(
    tmp_path: Path, payload: str
) -> None:
    path = tmp_path / "search.json"
    assert SS.read_quota(path) == []  # never searched
    path.write_text(payload, encoding="utf-8")
    with pytest.raises(R.InputError):
        SS.read_quota(path)


def test_a_failed_probe_is_recorded_with_its_error(tmp_path: Path) -> None:
    report, *_ = _run_search(
        tmp_path,
        _batch(_site(rerun=["country"])),
        ScriptedSearcher(),
        probe={"ok": False, "error": "http_401"},
    )
    assert report.quota_before is not None
    assert (report.quota_before["ok"], report.quota_before["error"]) == (False, "http_401")


def test_an_error_that_carries_no_status_is_ledgered_as_a_transport_failure(tmp_path: Path) -> None:
    error = MX.CodingPlanResponseError("the connection closed mid-body", http_status=None)
    report, _, ledger, _, _ = _run_search(
        tmp_path, _batch(_site(rerun=["country"])), ScriptedSearcher(*[error] * F.MAX_ATTEMPTS)
    )
    lines = _lines(ledger)
    assert [(x["outcome"], x["http_status"]) for x in lines] == [("transport_failure", None)] * 3
    assert report.outcomes[0].failure is not None


def test_the_real_searcher_is_built_only_from_a_key_and_a_base_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The settings are stood in for: this test reads no `.env` and holds no real key."""
    from pipeline.lyra import config as lyra_config

    def settings(key: str, base: str) -> Any:
        return lambda: types.SimpleNamespace(minimax_api_key=key, minimax_base_url=base)

    monkeypatch.setattr(lyra_config, "_get_settings", settings("", "https://api.minimax.io"))
    with pytest.raises(R.InputError, match="no MiniMax key"):
        SS.MiniMaxSearcher.from_settings()
    monkeypatch.setattr(lyra_config, "_get_settings", settings("k", ""))
    with pytest.raises(R.InputError, match="no MiniMax key"):
        SS.MiniMaxSearcher.from_settings()
    monkeypatch.setattr(
        lyra_config, "_get_settings", settings("k", "https://api.minimax.io/anthropic")
    )
    searcher = SS.MiniMaxSearcher.from_settings()
    try:
        assert searcher.endpoint == ENDPOINT
    finally:
        searcher.close()


def test_a_resumed_batch_with_every_search_on_disk_is_not_gated(tmp_path: Path) -> None:
    """The gate guards MiniMax requests; a batch that makes none must still reach its judge."""
    site = _site(rerun=["country"])
    _run_search(tmp_path, _batch(site), ScriptedSearcher())
    report, *_ = _run_search(
        tmp_path, _batch(site), ScriptedSearcher(), probe={"ok": False}, now=FRIDAY
    )
    assert report.stopped is None and not report.failed
    assert (report.quota_before, report.quota_after) == (None, None)
    half = _batch(site, _site("site-2", rerun=["country"]))
    report, *_ = _run_search(tmp_path, half, ScriptedSearcher(), probe={"ok": False})
    assert "did not answer" in str(report.stopped)  # one pending search is enough to be gated


def test_weather_is_retried_with_one_ledger_line_per_request(tmp_path: Path) -> None:
    searcher = ScriptedSearcher(
        MX.CodingPlanTransportError("reset"),
        MX.CodingPlanHTTPError("HTTP 503", http_status=503, body_bytes=9),
        _response("q", ("t", "https://e.org/a", "s", "")),
    )
    report, _, ledger, slept, _ = _run_search(tmp_path, _batch(_site(rerun=["country"])), searcher)
    assert report.outcomes[0].stored
    lines = _lines(ledger)
    assert [(x["attempt"], x["outcome"], x["http_status"]) for x in lines] == [
        (1, "transport_failure", None),
        (2, "http_error", 503),
        (3, "ok", 200),
    ]
    assert [x["given_up"] for x in lines] == [False, False, False]
    assert slept == list(F.RETRY_BACKOFF_SECONDS)


def test_a_search_that_keeps_failing_is_a_recorded_failure_not_no_hits(tmp_path: Path) -> None:
    searcher = ScriptedSearcher(*[MX.CodingPlanTransportError("reset")] * F.MAX_ATTEMPTS)
    report, store, ledger, _, _ = _run_search(tmp_path, _batch(_site(rerun=["country"])), searcher)
    (outcome,) = report.outcomes
    assert not outcome.stored and "search failed" in str(outcome.failure)
    assert not store.exists("site-1", "minimax_search.country")
    lines = _lines(ledger)
    assert len(lines) == F.MAX_ATTEMPTS and lines[-1]["given_up"] is True
    assert report.stopped is None


def test_a_client_error_is_asked_once(tmp_path: Path) -> None:
    searcher = ScriptedSearcher(MX.CodingPlanHTTPError("HTTP 400", http_status=400, body_bytes=3))
    report, _, ledger, slept, _ = _run_search(tmp_path, _batch(_site(rerun=["country"])), searcher)
    assert len(_lines(ledger)) == 1 and slept == []
    assert report.outcomes[0].failure is not None


def test_a_2xx_without_an_answer_is_retried_and_recorded_as_an_ok_request(tmp_path: Path) -> None:
    error = MX.CodingPlanResponseError("no organic", http_status=200, body_bytes=40)
    searcher = ScriptedSearcher(*[error] * F.MAX_ATTEMPTS)
    report, _, ledger, _, _ = _run_search(tmp_path, _batch(_site(rerun=["country"])), searcher)
    lines = _lines(ledger)
    assert [(x["outcome"], x["http_status"], x["bytes"]) for x in lines] == [("ok", 200, 40)] * 3
    assert report.outcomes[0].failure is not None


@pytest.mark.parametrize(
    "error",
    [
        MX.CodingPlanAuthError("base_resp 1004", http_status=200, body_bytes=10),
        MX.CodingPlanQuotaError("2056", http_status=200, body_bytes=10),
        MX.CodingPlanThrottleError("2062", http_status=429, body_bytes=10),
        MX.CodingPlanShapeError("organic is a str", http_status=200, body_bytes=10),
    ],
)
def test_a_stop_class_error_ends_the_stage_after_one_request(
    tmp_path: Path, error: Exception
) -> None:
    batch = _batch(
        _site("site-1", rerun=["country", "site_type"]), _site("site-2", rerun=["country"])
    )
    searcher = ScriptedSearcher(error)
    report, _, ledger, slept, _ = _run_search(tmp_path, batch, searcher)
    assert len(searcher.queries) == 1 and len(_lines(ledger)) == 1 and slept == []
    # `site_type` comes before `country` in the plan's field order, so it is the one that stopped.
    assert report.stopped is not None and "site-1/minimax_search.site_type" in report.stopped
    assert (
        len(report.outcomes) == 3
    )  # every slot is in the report, the unasked ones as not searched
    assert [o.failure is not None for o in report.outcomes] == [True, True, True]
    assert "not searched" in str(report.outcomes[-1].failure)


def test_a_hit_with_a_non_text_field_is_a_contract_break_that_stops_the_stage(
    tmp_path: Path,
) -> None:
    bad = MX.SearchResponse(
        query="q",
        items=(MX.WebSearchResult(title=5, url="https://e.org/a", snippet="s"),),  # type: ignore[arg-type]
        http_status=200,
        body_bytes=5,
    )
    report, store, *_ = _run_search(
        tmp_path, _batch(_site(rerun=["country"])), ScriptedSearcher(bad)
    )
    assert report.stopped is not None
    assert not store.exists("site-1", "minimax_search.country")


def test_a_null_title_or_date_is_stored_as_empty_text(tmp_path: Path) -> None:
    ok = MX.SearchResponse(
        query="q",
        items=(MX.WebSearchResult(title=None, url="https://e.org/a", snippet="s", date=None),),  # type: ignore[arg-type]
        http_status=200,
        body_bytes=5,
    )
    report, store, *_ = _run_search(
        tmp_path, _batch(_site(rerun=["country"])), ScriptedSearcher(ok)
    )
    record = SE.read_record(store.path_for("site-1", "minimax_search.country"))
    assert (record.hits[0].title, record.hits[0].date) == ("", "")


def test_the_gate_refusing_buys_no_search_and_writes_no_ledger_line(tmp_path: Path) -> None:
    searcher = ScriptedSearcher()
    report, _, ledger, _, waits = _run_search(
        tmp_path, _batch(_site(rerun=["country"])), searcher, probe={"ok": False, "error": "x"}
    )
    assert searcher.queries == [] and waits == [] and _lines(ledger) == []
    assert "did not answer" in str(report.stopped)
    assert "not searched" in str(report.outcomes[0].failure)


def test_a_batch_whose_sites_name_no_rerun_fields_is_not_a_search_batch(tmp_path: Path) -> None:
    with pytest.raises(R.InputError, match="rerun_fields"):
        _run_search(tmp_path, _batch(_site()), ScriptedSearcher())


def test_the_key_is_sent_in_a_header_and_written_nowhere(tmp_path: Path) -> None:
    key = "sk-cp-SECRET-key-for-this-test"
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            200,
            json={"base_resp": {"status_code": 0}, "organic": [{"title": "t", "link": "https://e.org/a", "snippet": "s"}]},
        )  # fmt: skip

    client = httpx.Client(
        base_url="https://api.minimax.io",
        headers={"Authorization": f"Bearer {key}"},
        transport=httpx.MockTransport(handler),
    )
    searcher = SS.MiniMaxSearcher(client)
    assert searcher.endpoint == ENDPOINT
    report, store, ledger, _, _ = _run_search(tmp_path, _batch(_site(rerun=["country"])), searcher)
    SS.write_report(tmp_path / "search.json", report)
    assert seen[0].headers["authorization"] == f"Bearer {key}"
    written = [ledger, tmp_path / "search.json", *store.root.glob("*.txt")]
    assert all(key not in path.read_text(encoding="utf-8") for path in written)


# ── the evidence the search adds, for the finder, the reviewer and the citation check ────────────


def test_a_site_without_rerun_fields_gets_exactly_the_evidence_it_had(tmp_path: Path) -> None:
    store = F.EvidenceStore(tmp_path / "evidence")
    _enwiki(store, "site-1")
    _store_search(store, "site-1", "country", _hit(1, "https://e.org/a"))  # a stray file
    excerpts = MS.evidence_excerpts(site_id="site-1", site=_site(), store=store)
    assert [e.feature for e in excerpts] == [F.FEATURE_ENWIKI]


def test_a_hit_becomes_one_excerpt_and_the_filters_drop_our_own_and_blocked_hosts(
    tmp_path: Path,
) -> None:
    store = F.EvidenceStore(tmp_path / "evidence")
    _enwiki(store, "site-1")
    _store_search(
        store,
        "site-1",
        "country",
        _hit(1, "https://e.org/a", title="Cave 1", snippet="The cave lies in Spain.", date="2019"),
        _hit(2, "https://ancientnerds.com/sites/es/cave-1", snippet="Spain"),
        _hit(3, "https://www.reddit.com/r/caves", snippet="Spain"),
    )
    excerpts = MS.evidence_excerpts(site_id="site-1", site=_site(rerun=["country"]), store=store)
    (hit,) = [e for e in excerpts if e.feature.startswith("minimax_search")]
    assert (hit.url, hit.text) == ("https://e.org/a", "Cave 1\nThe cave lies in Spain. (2019)")


def test_one_url_found_by_two_searches_is_one_page_carrying_both_texts(tmp_path: Path) -> None:
    store = F.EvidenceStore(tmp_path / "evidence")
    _enwiki(store, "site-1")
    _store_search(store, "site-1", "country", _hit(1, "https://e.org/a", snippet="In Spain."))
    _store_search(store, "site-1", "site_type", _hit(4, "https://e.org/a", snippet="A cave."))
    site = _site(rerun=["site_type", "country"])
    excerpts = MS.evidence_excerpts(site_id="site-1", site=site, store=store)
    pages = DS.pages_from_excerpts(excerpts)
    merged = [e for e in excerpts if e.url == "https://e.org/a"]
    assert len(merged) == 1
    assert merged[0].feature == "minimax_search.site_type+minimax_search.country"
    # Both quotes pass: with two excerpts under one url, the dict would keep only the second page.
    for quote in ("In Spain.", "A cave."):
        assert DS.claim_problems([DS.SourceClaim("https://e.org/a", quote)], pages) == ()


def test_a_quote_from_a_snippet_passes_and_a_fabricated_one_does_not(tmp_path: Path) -> None:
    store = F.EvidenceStore(tmp_path / "evidence")
    _enwiki(store, "site-1")
    _store_search(
        store, "site-1", "period_start", _hit(1, "https://e.org/a", snippet="Built c. 3000 BC.")
    )
    excerpts = MS.evidence_excerpts(
        site_id="site-1", site=_site(rerun=["period_start"]), store=store
    )
    pages = DS.pages_from_excerpts(excerpts)
    honest = DS.SourceClaim("https://e.org/a", "built c. 3000 BC.")
    invented = DS.SourceClaim("https://e.org/a", "Built c. 5000 BC.")
    assert DS.claim_problems([honest], pages) == ()
    assert DS.claim_problems([invented], pages) != ()


def test_a_hit_on_a_fetched_targets_url_raises_instead_of_hiding_a_page(tmp_path: Path) -> None:
    site = _site(rerun=["country"])
    store = F.EvidenceStore(tmp_path / "evidence")
    _enwiki(store, "site-1")
    enwiki_url = F.targets_for_site(site)[0].url
    _store_search(store, "site-1", "country", _hit(1, enwiki_url))
    with pytest.raises(MS.EvidenceUnusable, match="already a fetched target"):
        MS.evidence_excerpts(site_id="site-1", site=site, store=store)


def test_a_search_missing_with_no_record_raises_a_recorded_failure_is_named(
    tmp_path: Path,
) -> None:
    site = _site(rerun=["country"])
    store = F.EvidenceStore(tmp_path / "evidence")
    _enwiki(store, "site-1")
    with pytest.raises(MS.EvidenceUnusable, match="search report records no failure"):
        MS.evidence_excerpts(site_id="site-1", site=site, store=store)
    preview = MS.evidence_excerpts(site_id="site-1", site=site, store=store, allow_absent=True)
    assert preview[-1].feature == "minimax_search.country" and not preview[-1].present
    failed = MS.evidence_excerpts(
        site_id="site-1",
        site=site,
        store=store,
        failures={"minimax_search.country": "search failed: HTTP 503 (3 request(s) recorded)"},
    )
    assert failed[-1].failure is not None
    assert 'status="failed"' in MS.evidence_block(failed)
    assert MS.PARTIAL_EVIDENCE_NOTE in MS.failed_target_block(failed)


def test_search_failed_and_no_hits_reach_the_judge_as_two_different_facts(tmp_path: Path) -> None:
    """A failed search is a failed target in the prompt; an answered one with no hits is nothing."""
    batch = _batch(_site("site-1", rerun=["country"]), _site("site-2", rerun=["country"]))
    searcher = ScriptedSearcher(
        _response("q"),  # organic: [] - a real "no hits"
        *[MX.CodingPlanTransportError("reset")] * F.MAX_ATTEMPTS,
    )
    report, store, *_ = _run_search(tmp_path, batch, searcher)
    SS.write_report(tmp_path / "search.json", report)
    (tmp_path / "fetch.json").write_text(json.dumps({"sites": []}), encoding="utf-8")
    for site_id in ("site-1", "site-2"):
        _enwiki(store, site_id)
    failures = MS.read_fetch_failures(tmp_path / "fetch.json")
    assert list(failures) == ["site-2"]
    assert list(failures["site-2"]) == ["minimax_search.country"]
    no_hits = MS.evidence_excerpts(site_id="site-1", site=batch["sites"][0], store=store)
    failed = MS.evidence_excerpts(
        site_id="site-2", site=batch["sites"][1], store=store, failures=failures["site-2"]
    )
    assert [e.feature for e in no_hits] == [F.FEATURE_ENWIKI]
    assert [(e.feature, e.failure is not None) for e in failed][-1] == (
        "minimax_search.country",
        True,
    )


def test_a_site_failed_in_both_reports_keeps_both_failures(tmp_path: Path) -> None:
    """The two reports are merged per site: the search's failure must not replace the fetch's."""
    fetch = {"site_id": "s", "outcomes": [{"feature": "enwiki", "failure": "HTTP 404"}]}
    search = {"site_id": "s", "outcomes": [{"feature": "minimax_search.country", "failure": "x"}]}
    (tmp_path / "fetch.json").write_text(json.dumps({"sites": [fetch]}), encoding="utf-8")
    (tmp_path / "search.json").write_text(json.dumps({"sites": [search]}), encoding="utf-8")
    assert MS.read_fetch_failures(tmp_path / "fetch.json") == {
        "s": {"enwiki": "HTTP 404", "minimax_search.country": "x"}
    }


def test_a_failure_for_one_feature_in_both_reports_raises(tmp_path: Path) -> None:
    row = {"site_id": "s", "outcomes": [{"feature": "enwiki", "failure": "x"}]}
    (tmp_path / "fetch.json").write_text(json.dumps({"sites": [row]}), encoding="utf-8")
    (tmp_path / "search.json").write_text(json.dumps({"sites": [row]}), encoding="utf-8")
    with pytest.raises(R.InputError, match="both reports"):
        MS.read_fetch_failures(tmp_path / "fetch.json")


# ── the finder asks only the rerun fields ─────────────────────────────────────────────────────────


VOCAB = ("Cave Structures", "Temple")


def test_the_finder_asks_only_the_rerun_fields(tmp_path: Path) -> None:
    store = F.EvidenceStore(tmp_path / "evidence")
    _enwiki(store, "site-1")
    _store_search(store, "site-1", "period_start", _hit(1, "https://e.org/a"))
    _store_search(store, "site-1", "site_type", _hit(1, "https://e.org/b"))
    site = _site(rerun=["site_type", "period_start"])
    plan = DS.plan_site(batch_id="srch-0001", site=site, store=store, vocabulary=VOCAB)
    assert [c.call.field for c in plan.calls] == ["period_start", "site_type"]
    assert all("https://e.org/b" in c.call.prompt for c in plan.calls)
    assert all(
        text in plan.calls[0].call.prompt
        for text in ("VERDICT: CORRECT | WRONG | UNVERIFIABLE", "You propose; you do not write.")
    )


def test_an_over_bound_site_loses_only_its_rerun_fields(tmp_path: Path) -> None:
    store = F.EvidenceStore(tmp_path / "evidence")
    _enwiki(store, "site-1")
    big = "x" * (MS.MAX_EVIDENCE_CHARS + 1)
    _store_search(store, "site-1", "country", _hit(1, "https://e.org/a", snippet=big))
    plan = DS.plan_site(
        batch_id="srch-0001", site=_site(rerun=["country"]), store=store, vocabulary=VOCAB
    )
    assert plan.calls == []
    assert [s.field for s in plan.skipped] == ["country"]


def test_the_reviewer_reads_the_same_search_pages_and_checks_a_refutation_against_them(
    tmp_path: Path,
) -> None:
    store = F.EvidenceStore(tmp_path / "evidence")
    answers = F.EvidenceStore(tmp_path / "answers")
    _enwiki(store, "site-1")
    _store_search(store, "site-1", "country", _hit(1, "https://e.org/a", snippet="It is in Peru."))
    site = _site(rerun=["country"])
    answer = (
        "The snippet places it in Peru.\nVERDICT: WRONG\nPROPOSED: Peru\n"
        'SOURCE: https://e.org/a - "It is in Peru."\n'
    )
    path = answers.path_for("site-1", "country")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(answer, encoding="utf-8")
    plan = RS.plan_site(batch_id="srch-0001", site=site, answers=answers, store=store)
    (call,) = plan.calls
    assert call.call.field == "country" and "https://e.org/a" in call.call.prompt
    assert DS.source_problems(DS.parse_answer(answer), DS.pages_from_excerpts(call.excerpts)) == ()
    # The fields the search plan does not rerun have no answer here, so nobody is asked about them.
    assert {v.field for v in plan.unreviewable} == set(SP.DISCOVER_FIELDS) - {"country"}


def _review_plan(tmp_path: Path, site: dict[str, Any], field: str, proposed: str) -> Any:
    store = F.EvidenceStore(tmp_path / "evidence")
    answers = F.EvidenceStore(tmp_path / f"answers-{proposed}")
    _enwiki(store, "site-1")
    if not store.exists("site-1", "minimax_search.period_start"):
        _store_search(
            store, "site-1", "period_start", _hit(1, "https://e.org/a", snippet="Built in 500 BC.")
        )
    path = answers.path_for("site-1", field)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"The snippet dates it.\nVERDICT: WRONG\nPROPOSED: {proposed}\n"
        'SOURCE: https://e.org/a - "Built in 500 BC."\n',
        encoding="utf-8",
    )
    return RS.plan_site(batch_id="srch-0001", site=site, answers=answers, store=store)


@pytest.mark.parametrize(("kind", "decision"), [("held", "B7"), ("write_gate", "B8")])
def test_a_rerun_answer_that_repeats_an_unwritten_proposal_is_never_cleared(
    tmp_path: Path, kind: str, decision: str
) -> None:
    """B7/B8: the mass lane decided not to write this value. A rerun cannot write it back - with a
    new source or without one, re-opening that is Martin's call."""
    unwritten = {"period_start": {"change_key": "phase3:k1", "kind": kind, "proposed": "-500"}}
    site = _site(rerun=["period_start"], unwritten=unwritten)
    repeat = _review_plan(tmp_path, site, "period_start", "-0500")
    assert repeat.calls == []
    (verdict,) = [v for v in repeat.unreviewable if v.field == "period_start"]
    assert decision in str(verdict.unreviewable) and "phase3:k1" in str(verdict.unreviewable)
    assert not verdict.applies  # the writer acts on `applies` alone
    other = _review_plan(tmp_path, site, "period_start", "-600")
    assert [call.call.field for call in other.calls] == ["period_start"]


@pytest.mark.parametrize(
    "value",
    [
        None,
        [],
        {"country": {"change_key": "k", "kind": "held", "proposed": "Peru"}},  # not a rerun field
        {"period_start": {"change_key": "k", "kind": "held"}},
        {"period_start": {"change_key": "", "kind": "held", "proposed": "-500"}},
        {"period_start": {"change_key": "k", "kind": "hold", "proposed": "-500"}},
    ],
)
def test_a_damaged_unwritten_record_raises_instead_of_letting_a_held_value_through(
    value: Any,
) -> None:
    site = _site(rerun=["period_start"])
    site["rerun_unwritten"] = value
    with pytest.raises(R.InputError):
        SE.unwritten_proposals(site)
    assert SE.unwritten_proposals(_site()) == {}  # the mass run's records carry none


@pytest.mark.parametrize(
    ("one", "other", "same"),
    [("-500", "-0500", True), ("-500", " -500 ", True), ("Tomb", "tomb", True),
     ("Temple  complex", "temple complex", True), ("-500", "-600", False), ("Tomb", "Tombs", False)],
)  # fmt: skip
def test_a_repeat_is_recognised_across_case_spacing_and_leading_zeros(
    one: str, other: str, same: bool
) -> None:
    assert SE.same_value(one, other) is same


# ── the rerun plan ────────────────────────────────────────────────────────────────────────────────


def _source_run(
    tmp_path: Path, batches: dict[str, list[tuple[dict[str, Any], dict[str, str]]]]
) -> Path:
    """A mass run on disk: per batch an input, one enwiki page per site, a fetch report, answers."""
    root = tmp_path / "mass"
    for batch_id, rows in batches.items():
        batch_dir = root / batch_id
        batch_dir.mkdir(parents=True)
        sites = [site for site, _ in rows]
        payload = {
            "batch_id": batch_id,
            "ordinal": int(batch_id[-4:]),
            "pass": "discover",
            "sites": sites,
        }
        (batch_dir / "input.json").write_text(
            json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8"
        )
        (batch_dir / "fetch.json").write_text(
            json.dumps({"sites": [{"site_id": s["site_id"], "outcomes": []} for s in sites]}),
            encoding="utf-8",
        )
        store = F.EvidenceStore(batch_dir / "evidence")
        answers = F.EvidenceStore(batch_dir / "answers")
        for site, verdicts in rows:
            _enwiki(store, site["site_id"], f"{site['name']} text " + "y" * 50)
            for field, verdict in verdicts.items():
                path = answers.path_for(site["site_id"], field)
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(f"The evidence is silent.\nVERDICT: {verdict}\n", encoding="utf-8")
    return root  # noqa: RET504 - named for the reader


def _two_batches(tmp_path: Path) -> Path:
    return _source_run(
        tmp_path,
        {
            "batch-0001": [
                (_site("a"), {"period_start": "UNVERIFIABLE", "country": "CORRECT", "description": "UNVERIFIABLE"}),
                (_site("b"), {"period_start": "CORRECT"}),
            ],
            "batch-0002": [(_site("c"), {"site_type": "WRONG", "card_description": "UNVERIFIABLE"})],
            "batch-0003": [(_site("d"), {"country": "UNVERIFIABLE"})],
        },
    )  # fmt: skip


def test_the_plan_takes_only_undecided_fields_of_its_scope_verbatim_under_new_ids(
    tmp_path: Path,
) -> None:
    source = _two_batches(tmp_path)
    plan = _plan(source, "writable", "srch")
    assert [b["batch_id"] for b in plan.batches] == ["srch-0001", "srch-0003"]
    first = plan.batches[0]
    assert (first["ordinal"], first["pass"]) == (1, R.DISCOVER_PASS)
    assert first["source_run_dir"] == source.resolve().as_posix()
    (site,) = first["sites"]
    assert site["rerun_fields"] == ["period_start"]
    assert site["rerun_why"] == {"period_start": SPL.WHY_UNVERIFIABLE}
    assert site["rerun_unwritten"] == {}
    assert site["query_values"] == {"country": "Spain", "site_type": "Cave Structures"}
    assert site["source_batch"] == "batch-0001"
    assert {k: v for k, v in site.items() if k not in SPL.ADDED_SITE_KEYS} == _site("a")
    text = _plan(source, "text", "srtx")
    assert [(b["batch_id"], b["sites"][0]["rerun_fields"]) for b in text.batches] == [
        ("srtx-0001", ["description"]),
        ("srtx-0002", ["card_description"]),
    ]


def test_the_plan_is_byte_identical_across_builds(tmp_path: Path) -> None:
    source = _two_batches(tmp_path)
    one = _plan(source, "all", "srch").text()
    two = _plan(source, "all", "srch").text()
    assert one == two and one.endswith("\n") and "\r" not in one


@pytest.mark.parametrize("prefix", ["batch", "SRCH", "s", "srch1"])
def test_a_prefix_that_could_collide_or_is_not_letters_is_refused(
    tmp_path: Path, prefix: str
) -> None:
    with pytest.raises(R.InputError, match="prefix"):
        _plan(_two_batches(tmp_path), "all", prefix)


def test_a_query_value_is_productions_and_a_field_production_changed_is_not_rerun(
    tmp_path: Path,
) -> None:
    """The snapshot is older than production. A query reads production's value (another lane may
    have corrected it), and a rerun field whose value production no longer holds is left out and
    listed: the finder would judge a value that is not there any more."""
    source = _two_batches(tmp_path)
    current = _current_of(source)
    current["a"]["country"] = "Portugal"  # a reruns period_start; its query reads the country
    current["d"]["country"] = "Andorra"  # d reruns country, and production changed it
    plan = _plan(source, "writable", "srch", current=current)
    by_site = {s["site_id"]: s for b in plan.batches for s in b["sites"]}
    assert by_site["a"]["query_values"]["country"] == "Portugal"
    assert "d" not in by_site and [b["batch_id"] for b in plan.batches] == ["srch-0001"]
    assert plan.summary()["changed_in_production"] == [
        {"field": "country", "production": "Andorra", "site_id": "d", "snapshot": "Spain"}
    ]
    del current["a"]
    with pytest.raises(R.InputError, match="lacks this site"):
        _plan(source, "writable", "srch", current=current)


@pytest.mark.parametrize(
    ("lines", "match"),
    [
        (['{"site_id": "a", "country": "Spain", "site_type": "T", "period_start": 1}'] * 2, "twice"),
        (['{"site_id": "a", "country": "Spain", "site_type": "T"}'], "exactly"),
        (['{"site_id": "a", "country": "Spain", "site_type": "T", "period_start": 1, "x": 2}'], "exactly"),
        ([], "empty"),
    ],
)  # fmt: skip
def test_a_partial_or_damaged_export_of_production_is_refused(
    tmp_path: Path, lines: list[str], match: str
) -> None:
    path = tmp_path / "current.jsonl"
    path.write_text("".join(line + "\n" for line in lines), encoding="utf-8")
    with pytest.raises(R.InputError, match=match):
        SPL.read_current_values(path)


def test_the_export_command_reads_back_as_the_values_the_plan_needs(tmp_path: Path) -> None:
    """psql's `json_build_object(...)::text` spells `"key" : value`; the reader takes it as it is."""
    path = tmp_path / "current.jsonl"
    path.write_text(
        '{"site_id" : "a", "country" : "Spain", "site_type" : "Settlement", "period_start" : -3500}\n',
        encoding="utf-8",
    )
    assert SPL.read_current_values(path) == {
        "a": {"period_start": -3500, "site_type": "Settlement", "country": "Spain"}
    }
    assert all(name in SPL.CURRENT_VALUES_SQL for name in ("site_id", *SPL.CURRENT_VALUE_FIELDS))


def test_a_source_batch_that_is_not_its_own_discover_batch_is_refused(tmp_path: Path) -> None:
    source = _two_batches(tmp_path)
    path = source / "batch-0002" / "input.json"
    batch = json.loads(path.read_text(encoding="utf-8"))
    path.write_text(json.dumps({**batch, "batch_id": "batch-0009"}) + "\n", encoding="utf-8")
    with pytest.raises(R.InputError, match="does not hold exactly batch batch-0002"):
        _plan(source, "all", "srch")
    path.write_text(json.dumps({**batch, "pass": "worklist"}) + "\n", encoding="utf-8")
    with pytest.raises(R.InputError, match="not a discover batch"):
        _plan(source, "all", "srch")


def _write_rows(
    tmp_path: Path, rows: list[dict[str, Any]], written: list[str], holds: list[dict[str, Any]]
) -> tuple[Path, Path, Path]:
    all_rows = tmp_path / "ALL_ROWS.jsonl"
    all_rows.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    keys = tmp_path / "written.txt"
    keys.write_text("".join(k + "\n" for k in written), encoding="utf-8")
    hold_path = tmp_path / "HOLDS.jsonl"
    hold_path.write_text("".join(json.dumps(h) + "\n" for h in holds), encoding="utf-8")
    return all_rows, keys, hold_path


ROWS = [
    {"change_key": "k1", "site_id": "c", "column": "site_type", "batch_id": "batch-0002",
     "old_value": "Cave Structures", "new_value": "Temple"},
    {"change_key": "k2", "site_id": "b", "column": "country", "batch_id": "batch-0001",
     "old_value": "Spain", "new_value": "Portugal"},
    {"change_key": "k3", "site_id": "a", "column": "site_type", "batch_id": "batch-0001",
     "old_value": "Cave Structures", "new_value": "Tomb"},
]  # fmt: skip


def _row(site_id: str, column: str, batch_id: str, *, old: str | None = "Spain") -> Any:
    return SPL.UnwrittenRow(
        batch_id=batch_id, why=SPL.WHY_GATE, kind="write_gate", change_key=f"k-{site_id}",
        old_value=old, proposed="Peru",
    )  # fmt: skip


def test_held_and_gate_stopped_rows_are_rerun_and_written_rows_are_not(tmp_path: Path) -> None:
    all_rows, keys, holds = _write_rows(
        tmp_path, ROWS, ["k3"], [{"change_key": "k1", "hold_reason": "not proven"}]
    )
    extra = SPL.unwritten_rows(all_rows=all_rows, written_keys=keys, holds=holds)
    assert extra == {
        ("c", "site_type"): SPL.UnwrittenRow(
            "batch-0002", SPL.WHY_HELD.format(reason="not proven"), "held", "k1", "Cave Structures",
            "Temple",
        ),
        ("b", "country"): SPL.UnwrittenRow(
            "batch-0001", SPL.WHY_GATE, "write_gate", "k2", "Spain", "Portugal"
        ),
    }  # fmt: skip
    plan = _plan(_two_batches(tmp_path), "writable", "srch", extra=extra)
    by_site = {s["site_id"]: s for b in plan.batches for s in b["sites"]}
    assert by_site["c"]["rerun_fields"] == ["site_type"]
    assert by_site["b"]["rerun_why"] == {"country": SPL.WHY_GATE}
    assert "site_type" not in by_site["a"]["rerun_fields"]  # k3 was written
    assert plan.summary()["fields_by_reason"] == {"held": 1, "unverifiable": 2, "write_gate": 1}
    # The old proposal travels along, so the reviewer can refuse a rerun that repeats it.
    assert by_site["c"]["rerun_unwritten"] == {
        "site_type": {"change_key": "k1", "kind": "held", "proposed": "Temple"}
    }
    assert SE.unwritten_proposals(by_site["b"]) == {
        "country": SE.UnwrittenProposal(change_key="k2", proposed="Portugal", kind="write_gate")
    }
    assert by_site["a"]["rerun_unwritten"] == {}


@pytest.mark.parametrize(
    ("written", "holds", "match"),
    [
        (["k9"], [], "not planned rows"),
        (["k1"], [{"change_key": "k1", "hold_reason": "x"}], "written after all"),
        ([], [{"change_key": "k9", "hold_reason": "x"}], "not planned rows"),
    ],
)
def test_the_three_write_records_must_agree(
    tmp_path: Path, written: list[str], holds: list[dict[str, Any]], match: str
) -> None:
    all_rows, keys, hold_path = _write_rows(tmp_path, ROWS, written, holds)
    with pytest.raises(R.InputError, match=match):
        SPL.unwritten_rows(all_rows=all_rows, written_keys=keys, holds=hold_path)


@pytest.mark.parametrize(
    ("change", "match"),
    [
        ({"change_key": "k4"}, "planned twice"),  # a second row for (c, site_type)
        ({"change_key": "k4", "site_id": "d", "new_value": " "}, "no proposed new_value"),
        ({"change_key": "k4", "site_id": "d", "old_value": 7}, "not text"),
    ],
)
def test_an_unwritten_row_without_its_proposal_or_planned_twice_is_refused(
    tmp_path: Path, change: dict[str, Any], match: str
) -> None:
    rows = [*ROWS, {**ROWS[0], **change}]
    all_rows, keys, hold_path = _write_rows(tmp_path, rows, ["k3"], [])
    with pytest.raises(R.InputError, match=match):
        SPL.unwritten_rows(all_rows=all_rows, written_keys=keys, holds=hold_path)


def test_an_unwritten_row_that_finds_no_site_or_the_wrong_batch_raises(tmp_path: Path) -> None:
    source = _two_batches(tmp_path)
    with pytest.raises(R.InputError, match="found no site"):
        _plan(
            source,
            "writable",
            "srch",
            extra={("zz", "country"): _row("zz", "country", "batch-0001")},
        )
    with pytest.raises(R.InputError, match="puts it in batch-0002"):
        _plan(
            source, "writable", "srch", extra={("a", "country"): _row("a", "country", "batch-0002")}
        )
    with pytest.raises(R.InputError, match="scope"):
        _plan(source, "text", "srtx", extra={("a", "country"): _row("a", "country", "batch-0001")})


def test_an_unwritten_row_that_disagrees_with_the_snapshot_or_the_answers_raises(
    tmp_path: Path,
) -> None:
    source = _two_batches(tmp_path)
    with pytest.raises(R.InputError, match="old value"):
        _plan(
            source,
            "writable",
            "srch",
            extra={("b", "country"): _row("b", "country", "batch-0001", old="Mexico")},
        )
    # a's period_start is UNVERIFIABLE: it was never a planned write.
    both = {("a", "period_start"): _row("a", "period_start", "batch-0001", old="-3000")}
    with pytest.raises(R.InputError, match="both UNVERIFIABLE and a planned write"):
        _plan(source, "writable", "srch", extra=both)


def test_a_selection_keeps_only_its_sites_and_names_the_ones_it_cannot_find(
    tmp_path: Path,
) -> None:
    source = _two_batches(tmp_path)
    plan = _plan(source, "all", "srgd", site_ids=["c"])
    assert [s["site_id"] for b in plan.batches for s in b["sites"]] == ["c"]
    with pytest.raises(R.InputError, match="in no source batch"):
        _plan(source, "all", "srgd", site_ids=["nope"])


@pytest.mark.parametrize(("site_id", "field"), [("ghost", "country"), ("a", "name")])
def test_an_answer_nobody_can_place_is_refused(tmp_path: Path, site_id: str, field: str) -> None:
    source = _two_batches(tmp_path)
    stray = F.EvidenceStore(source / "batch-0001" / "answers").path_for(site_id, field)
    stray.write_text("VERDICT: UNVERIFIABLE\n", encoding="utf-8")
    with pytest.raises(R.InputError, match="lacks"):
        _plan(source, "all", "srch")


def test_a_source_that_is_already_a_rerun_is_refused(tmp_path: Path) -> None:
    source = _source_run(
        tmp_path, {"batch-0001": [(_site("a", rerun=["country"]), {"country": "UNVERIFIABLE"})]}
    )
    with pytest.raises(R.InputError, match="already carries"):
        _plan(source, "all", "srch")


def test_the_plan_counts_the_queries_that_still_carry_the_value_under_test(
    tmp_path: Path,
) -> None:
    source = _source_run(
        tmp_path,
        {"batch-0001": [
            (_site("a", name="Runestones of Spain"), {"country": "UNVERIFIABLE"}),
            (_site("b", name="Stina, Spain"), {"country": "UNVERIFIABLE"}),
            (_site("c", name="Cave Structures of Uxmal"), {"site_type": "UNVERIFIABLE", "country": "UNVERIFIABLE"}),
        ]},
    )  # fmt: skip
    summary = _plan(source, "writable", "srch").summary()
    # a carries its country, b loses the ", Spain" suffix, c carries its site type.
    assert summary["queries_still_carry_the_value_under_test"] == {"country": 1, "site_type": 1}


# ── prepare copies the source evidence, byte for byte, and only reads the source ─────────────────


def _digest_tree(root: Path) -> dict[str, str]:
    return {
        str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(root.rglob("*"))
        if p.is_file()
    }


def test_prepare_copies_byte_identically_twice_and_leaves_the_source_untouched(
    tmp_path: Path,
) -> None:
    source = _two_batches(tmp_path)
    before = _digest_tree(source)
    plan = _plan(source, "writable", "srch")
    batch = plan.batches[0]
    target = tmp_path / "search1" / batch["batch_id"]
    assert SPL.prepare_search_batch(batch, target) == {
        "evidence_copied": 1,
        "evidence_already_there": 0,
    }
    assert SPL.prepare_search_batch(batch, target) == {
        "evidence_copied": 0,
        "evidence_already_there": 1,
    }
    src = source / "batch-0001"
    assert (target / "fetch.json").read_bytes() == (src / "fetch.json").read_bytes()
    slug = F.EvidenceStore.slug("a", F.FEATURE_ENWIKI) + ".txt"
    assert (target / "evidence" / slug).read_bytes() == (src / "evidence" / slug).read_bytes()
    assert not (target / "answers").exists()  # a fresh answer store: the old answer is never reused
    assert _digest_tree(source) == before


def test_prepare_refuses_a_changed_record_a_changed_copy_and_a_hole(tmp_path: Path) -> None:
    source = _two_batches(tmp_path)
    batch = _plan(source, "writable", "srch").batches[0]
    target = tmp_path / "search1" / "srch-0001"
    drifted = json.loads(json.dumps(batch))
    drifted["sites"][0]["name"] = "Another cave"
    with pytest.raises(R.InputError, match="differs"):
        SPL.prepare_search_batch(drifted, target)
    SPL.prepare_search_batch(batch, target)
    (target / "fetch.json").write_text("{}", encoding="utf-8")
    with pytest.raises(F.EvidenceConflict):
        SPL.prepare_search_batch(batch, target)
    (target / "fetch.json").unlink()
    (source / "batch-0001" / "evidence" / (F.EvidenceStore.slug("a", "enwiki") + ".txt")).unlink()
    with pytest.raises(R.InputError, match="records no failure"):
        SPL.prepare_search_batch(batch, tmp_path / "other" / "srch-0001")


def test_prepare_refuses_a_source_input_that_is_not_the_batch_the_plan_names(
    tmp_path: Path,
) -> None:
    source = _two_batches(tmp_path)
    batch = _plan(source, "writable", "srch").batches[0]
    path = source / "batch-0001" / "input.json"
    record = json.loads(path.read_text(encoding="utf-8"))
    path.write_text(json.dumps({**record, "batch_id": "batch-0002"}) + "\n", encoding="utf-8")
    with pytest.raises(R.InputError, match="does not hold exactly batch batch-0001"):
        SPL.prepare_search_batch(batch, tmp_path / "search1" / "srch-0001")


def test_prepare_refuses_a_batch_whose_sites_come_from_two_source_batches(tmp_path: Path) -> None:
    source = _two_batches(tmp_path)
    plan = _plan(source, "all", "srch")
    mixed = dict(plan.batches[0])
    mixed["sites"] = plan.batches[0]["sites"] + plan.batches[1]["sites"]
    with pytest.raises(R.InputError, match="not one source batch"):
        SPL.prepare_search_batch(mixed, tmp_path / "x")


# ── the budget dry run ────────────────────────────────────────────────────────────────────────────


def test_the_budget_dry_run_counts_the_sites_a_search_could_push_over_the_bound(
    tmp_path: Path,
) -> None:
    near = _site("near")
    far = _site("far")
    source = _source_run(
        tmp_path,
        {"batch-0001": [(near, {"country": "UNVERIFIABLE"}), (far, {"country": "UNVERIFIABLE"})]},
    )
    store = F.EvidenceStore(source / "batch-0001" / "evidence")
    _enwiki(store, "near", "z" * (MS.MAX_EVIDENCE_CHARS - 5_000))
    plan = _plan(source, "writable", "srch")
    report = SPL.budget_report(plan.batches, hits_per_search=10, chars_per_hit=1000)
    assert report["sites"] == 2 and report["searches"] == 2
    assert report["sites_pushed_over_the_bound"] == 1
    assert report["sites_staying_under"] == 1
    assert report["hits_per_search_every_site_fits"] == 5
    assert report["evidence_chars_max"] == MS.MAX_EVIDENCE_CHARS - 5_000


# ── the CLI ───────────────────────────────────────────────────────────────────────────────────────


def _prepared_search_run(tmp_path: Path, scope: str = "writable") -> tuple[Path, str]:
    source = _two_batches(tmp_path)
    plan_path = tmp_path / "PLAN.search.jsonl"
    SPL.write_plan(plan_path, _plan(source, scope, "srch"))
    run_dir = tmp_path / "search1"
    assert (
        R.main(
            [
                "prepare",
                "--plan",
                str(plan_path),
                "--run-dir",
                str(run_dir),
                "--batch-id",
                "srch-0001",
            ]
        )
        == 0
    )
    return run_dir, "srch-0001"


def _current_file(tmp_path: Path, source: Path) -> Path:
    """The read-only export of production's values, as `CURRENT_VALUES_SQL` prints it."""
    path = tmp_path / "current.jsonl"
    rows = [{"site_id": site_id, **values} for site_id, values in _current_of(source).items()]
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    return path


def test_plan_search_needs_productions_values_and_the_written_keys_outside_the_text_scope(
    tmp_path: Path,
) -> None:
    source = _two_batches(tmp_path)
    current = _current_file(tmp_path, source)
    out = str(tmp_path / "p.jsonl")
    with pytest.raises(R.InputError, match="--current-values is required"):
        R.main(["plan-search", "--scope", "text", "--source-run-dir", str(source), "--out", out])
    with pytest.raises(R.InputError, match="--written-keys is required"):
        R.main(["plan-search", "--source-run-dir", str(source), "--current-values", str(current),
                "--out", out])  # fmt: skip
    all_rows, keys, holds = _write_rows(tmp_path, ROWS, ["k3"], [])
    with pytest.raises(R.InputError, match="text scope"):
        R.main(["plan-search", "--scope", "text", "--source-run-dir", str(source),
                "--current-values", str(current), "--written-keys", str(keys), "--out", out])  # fmt: skip
    code = R.main(
        ["plan-search", "--source-run-dir", str(source), "--all-rows", str(all_rows), "--holds", str(holds),
         "--written-keys", str(keys), "--current-values", str(current), "--out", out]
    )  # fmt: skip
    assert code == 0
    plan = R.read_jsonl(tmp_path / "p.jsonl")
    assert sum(len(s["rerun_fields"]) for b in plan for s in b["sites"]) == 4


def _gold(tmp_path: Path, records: Any) -> Path:
    path = tmp_path / "gold_sites.json"
    path.write_text(json.dumps({"records": records}), encoding="utf-8")
    return path


def test_the_pilot_selects_the_gold_standards_own_sites(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source = _two_batches(tmp_path)
    base = ["plan-search", "--scope", "all", "--prefix", "srgd", "--source-run-dir", str(source),
            "--current-values", str(_current_file(tmp_path, source)), "--written-keys",
            str(_write_rows(tmp_path, [], [], [])[1]), "--all-rows", str(_write_rows(tmp_path, [], [], [])[0]),
            "--holds", str(tmp_path / "HOLDS.jsonl"), "--out", str(tmp_path / "gold.jsonl")]  # fmt: skip
    capsys.readouterr()
    assert (
        R.main([*base, "--gold-sites", str(_gold(tmp_path, [{"site_id": "c"}, {"site_id": "d"}]))])
        == 0
    )
    summary = json.loads(capsys.readouterr().out)
    assert (summary["sites"], summary["fields"]) == (2, 2)
    ids = tmp_path / "ids.txt"
    ids.write_text("c\n", encoding="utf-8")
    with pytest.raises(R.InputError, match="two selections"):
        R.main(
            [
                *base,
                "--gold-sites",
                str(_gold(tmp_path, [{"site_id": "c"}])),
                "--site-ids",
                str(ids),
            ]
        )
    for records, match in (
        ([{"site_id": "c"}, {"site_id": "c"}], "one site twice"),
        ([{"site_id": ""}], "without a site_id"),
        ([], "no `records` list"),
    ):
        with pytest.raises(R.InputError, match=match):
            R.main([*base, "--gold-sites", str(_gold(tmp_path, records))])


def test_search_without_live_lists_the_queries_and_buys_nothing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    run_dir, batch_id = _prepared_search_run(tmp_path)
    capsys.readouterr()

    def refuse(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("a dry run must not build a searcher or probe the quota")

    monkeypatch.setattr(SS.MiniMaxSearcher, "from_settings", refuse)
    monkeypatch.setattr(MX, "probe_minimax_quota", refuse)
    ledger = tmp_path / "LEDGER.jsonl"
    assert (
        R.main(
            ["search", "--run-dir", str(run_dir), "--batch-id", batch_id, "--ledger", str(ledger)]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["searches_pending"] == 1
    assert payload["slots"][0]["query"].startswith('"Cave 1"')
    assert payload["slots"][0]["carries"] == []
    assert not ledger.exists()


class _ClosingSearcher(ScriptedSearcher):
    closed = False

    def close(self) -> None:
        self.closed = True


@pytest.mark.parametrize(
    ("script", "probe", "code"),
    [
        ([], PROBE_OK, 0),
        ([MX.CodingPlanHTTPError("HTTP 400", http_status=400, body_bytes=1)], PROBE_OK, R.SEARCH_INCOMPLETE_EXIT),
        ([MX.CodingPlanQuotaError("2056", http_status=200, body_bytes=1)], PROBE_OK, R.STOP_RUN_EXIT),
        ([], {"ok": False, "error": "no_api_key_or_base_url"}, R.STOP_RUN_EXIT),
    ],
)  # fmt: skip
def test_search_live_writes_its_report_and_exits_with_what_happened(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    script: list[Any],
    probe: dict[str, Any],
    code: int,
) -> None:
    run_dir, batch_id = _prepared_search_run(tmp_path)
    capsys.readouterr()
    searcher = _ClosingSearcher(*script)
    monkeypatch.setattr(SS.MiniMaxSearcher, "from_settings", classmethod(lambda cls: searcher))
    monkeypatch.setattr(MX, "probe_minimax_quota", lambda force=False: dict(probe))
    monkeypatch.setattr(SS, "utc_now", lambda: TUESDAY)
    argv = ["search", "--live", "--run-dir", str(run_dir), "--batch-id", batch_id,
            "--ledger", str(tmp_path / "L.jsonl"), "--pacing-dir", str(tmp_path / "pace")]  # fmt: skip
    assert R.main(argv) == code
    assert searcher.closed
    payload = json.loads(capsys.readouterr().out)
    report = json.loads((run_dir / batch_id / "search.json").read_text(encoding="utf-8"))
    (entry,) = report["quota"]
    assert entry["before"]["ok"] is (probe["ok"] is True)
    assert ("error" in payload) is (code == R.STOP_RUN_EXIT)
    # A second run reads the first run's readings back and keeps them.
    assert R.main(argv) in (0, R.SEARCH_INCOMPLETE_EXIT, R.STOP_RUN_EXIT)
    again = json.loads((run_dir / batch_id / "search.json").read_text(encoding="utf-8"))
    assert again["quota"][0] == entry


def test_search_live_without_a_key_stops_the_run_and_asks_nothing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    run_dir, batch_id = _prepared_search_run(tmp_path)
    capsys.readouterr()

    def no_key(cls: Any) -> Any:
        raise R.InputError("LyraSettings carries no MiniMax key or base url")

    def refuse(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("no key, so nothing may be probed")

    monkeypatch.setattr(SS.MiniMaxSearcher, "from_settings", classmethod(no_key))
    monkeypatch.setattr(MX, "probe_minimax_quota", refuse)
    argv = ["search", "--live", "--run-dir", str(run_dir), "--batch-id", batch_id,
            "--ledger", str(tmp_path / "L.jsonl"), "--pacing-dir", str(tmp_path / "pace")]  # fmt: skip
    assert R.main(argv) == R.STOP_RUN_EXIT
    assert "no MiniMax key" in json.loads(capsys.readouterr().out)["error"]
    assert not (tmp_path / "L.jsonl").exists()


# ── the mass driver's part ────────────────────────────────────────────────────────────────────────


def _search_plan_file(tmp_path: Path) -> Path:
    source = _two_batches(tmp_path)
    path = tmp_path / "PLAN.search.jsonl"
    SPL.write_plan(path, _plan(source, "all", "srch"))
    return path


def test_the_driver_reads_a_search_plan_as_rerun_calls_and_searches(tmp_path: Path) -> None:
    batches = MR.read_plan(_search_plan_file(tmp_path))
    assert [(b.batch_id, b.search, b.expected_calls, b.searches) for b in batches] == [
        ("srch-0001", True, 2, 2),
        ("srch-0002", True, 1, 1),
        ("srch-0003", True, 1, 1),
    ]


def test_a_plan_line_with_mixed_or_damaged_rerun_fields_is_refused_with_its_line(
    tmp_path: Path,
) -> None:
    path = tmp_path / "PLAN.jsonl"
    mixed = {
        "batch_id": "srch-0001",
        "ordinal": 1,
        "sites": [_site("a", rerun=["country"]), _site("b")],
    }
    path.write_text(json.dumps(mixed) + "\n", encoding="utf-8")
    with pytest.raises(MR.PlanError, match=":1: some sites"):
        MR.read_plan(path)
    damaged = {"batch_id": "srch-0001", "ordinal": 1, "sites": [_site("a", rerun=[])]}
    path.write_text(json.dumps(damaged) + "\n", encoding="utf-8")
    with pytest.raises(MR.PlanError, match=":1: "):
        MR.read_plan(path)


def test_the_stage_sequence_must_fit_the_plan(tmp_path: Path) -> None:
    plan = _search_plan_file(tmp_path)
    with pytest.raises(MR.PlanError, match="does not fit"):
        MR.main(
            ["--plan", str(plan), "--run-dir", str(tmp_path / "r"), "--ledger", str(tmp_path / "L")]
        )
    assert MR.main(["--plan", str(plan), "--run-dir", str(tmp_path / "r"), "--ledger", str(tmp_path / "L"),
                    "--stages", "prepare,search,judge"]) == 0  # fmt: skip


def test_every_search_lane_argv_is_accepted_by_the_real_cli(tmp_path: Path) -> None:
    runner = MR.StageRunner(
        plan=tmp_path / "PLAN.jsonl",
        run_dir=tmp_path / "runs",
        ledger=tmp_path / "L.jsonl",
        log_dir=tmp_path / "logs",
        live=True,
        request_timeout=30.0,
        python=Path("python"),
        runner=Path("run.py"),
        stages=MR.SEARCH_STAGES,
    )
    parser = R.build_parser()
    for stage in MR.SEARCH_STAGES:
        parser.parse_args(runner.argv(stage, "srch-0001")[2:])
    search = parser.parse_args(runner.argv("search", "srch-0001")[2:])
    assert search.live and search.pacing_dir == str(MR.DEFAULT_PACING_DIR)
    assert search.ledger == str(tmp_path / "L.jsonl")
    with pytest.raises(MR.PlanError):
        MR.StageRunner(
            plan=tmp_path / "P", run_dir=tmp_path, ledger=tmp_path / "L", log_dir=tmp_path,
            live=True, stages=("prepare", "judge"),
        )  # fmt: skip


def _drive_one_search(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    script: list[Any],
    batches: int,
    probe: dict[str, Any] | None = None,
) -> tuple[int, Any, list[str]]:
    """The mass driver over a prepared search batch whose `search` stage is the **real** command,
    run in-process with a scripted searcher: the driver reads exactly what `run.py search` prints."""
    run_dir, batch_id = _prepared_search_run(tmp_path, scope="all")  # site a: text + period_start
    searcher = _ClosingSearcher(*script)
    monkeypatch.setattr(SS.MiniMaxSearcher, "from_settings", classmethod(lambda cls: searcher))
    monkeypatch.setattr(MX, "probe_minimax_quota", lambda force=False: dict(probe or PROBE_OK))
    monkeypatch.setattr(SS, "utc_now", lambda: TUESDAY)
    started: list[str] = []

    def fake_run(argv: list[str], **kwargs: Any) -> Any:
        stage = argv[2]
        started.append(stage)
        if stage != "search":
            return types.SimpleNamespace(returncode=0)
        with contextlib.redirect_stdout(kwargs["stdout"]):
            code = R.main([str(part) for part in argv[2:]])
        return types.SimpleNamespace(returncode=code)

    monkeypatch.setattr(MR.subprocess, "run", fake_run)
    runner = MR.StageRunner(
        plan=tmp_path / "PLAN.search.jsonl", run_dir=run_dir, ledger=tmp_path / "L.jsonl",
        log_dir=tmp_path / "logs", live=True, python=Path("python"), runner=Path("run.py"),
        pacing_dir=tmp_path / "pace", stages=MR.SEARCH_STAGES,
    )  # fmt: skip
    planned = [MR.PlannedBatch(batch_id, 1, 1, 2, 2), MR.PlannedBatch("srch-0002", 2, 1, 1, 1)]
    progress = MR.Progress(plan="p", run_dir=str(run_dir), live=True, jobs=1, batches_total=batches)
    code = MR.run_mass(
        batches=planned[:batches],
        runner=runner,
        budget=MR.Budget(),
        ledger=tmp_path / "L.jsonl",
        progress=progress,
        progress_path=tmp_path / "progress.json",
        jobs=1,
        stop_of=lambda: runner.stop_reason,
    )
    return code, progress, started


@pytest.mark.parametrize(
    ("error", "cause"),
    [
        (MX.CodingPlanQuotaError("base_resp 2056: usage limit reached", http_status=200, body_bytes=9), "2056"),
        (MX.CodingPlanThrottleError("HTTP 429: (2062)", http_status=429, body_bytes=9), "2062"),
        (MX.CodingPlanAuthError("HTTP 401: invalid key", http_status=401, body_bytes=9), "401"),
    ],
)  # fmt: skip
def test_a_search_that_asks_the_run_to_stop_stops_it_and_says_why(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, error: Exception, cause: str
) -> None:
    """The stop-class error arrives on the second search, after one answered request: the printed
    report then carries `attempts[].error: null` lines below its own `error`, which a bottom-up
    read took for the reason."""
    ok = _response("q", ("t", "https://e.org/a", "s", ""))
    code, progress, started = _drive_one_search(
        tmp_path, monkeypatch, script=[ok, error], batches=2
    )
    assert code == 1
    assert started == ["prepare", "search"]  # the judge never ran, the second batch never started
    assert cause in str(progress.stopped) and "search stopped" in str(progress.stopped)
    assert progress.not_reached == ["srch-0002"]
    assert len(progress.quota["srch-0001"]) == 1  # the readings of the stopped run are kept


def test_the_gate_refusal_is_the_reason_not_the_probes_nested_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    code, progress, _ = _drive_one_search(
        tmp_path, monkeypatch, script=[], batches=1, probe={"ok": False, "error": "http_401"}
    )
    assert code == 1
    # One batch only: no later guard reads the stop, so the end of the run has to record it.
    assert "the quota probe did not answer" in str(progress.stopped)


def test_the_stop_reason_is_read_from_this_calls_output_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The stage log is appended to across runs; an earlier run's reason must not be reported."""
    logs = tmp_path / "logs"
    logs.mkdir()
    old = json.dumps({"error": "search stopped: an older reason"}, indent=1, sort_keys=True)
    (logs / "srch-0001.search.log").write_text(old + "\n", encoding="utf-8")

    def fake_run(argv: list[str], **kwargs: Any) -> Any:
        return types.SimpleNamespace(returncode=R.STOP_RUN_EXIT if argv[2] == "search" else 0)

    monkeypatch.setattr(MR.subprocess, "run", fake_run)
    runner = MR.StageRunner(
        plan=tmp_path / "P", run_dir=tmp_path / "runs", ledger=tmp_path / "L.jsonl", log_dir=logs,
        live=True, python=Path("python"), runner=Path("run.py"), stages=MR.SEARCH_STAGES,
    )  # fmt: skip
    runner.batch(MR.PlannedBatch("srch-0001", 1, 1, 1, 1))
    assert runner.stop_reason == "srch-0001: search stopped the run: None"


def test_only_a_reports_own_error_key_is_its_error() -> None:
    printed = json.dumps(
        {
            "error": "search stopped: 2056",
            "sites": [{"outcomes": [{"attempts": [{"error": None}]}]}],
        },
        indent=1,
        sort_keys=True,
    )
    assert MR.report_error(printed) == "search stopped: 2056"
    nested_only = json.dumps({"sites": [{"error": "x"}]}, indent=1, sort_keys=True)
    assert MR.report_error(nested_only) is None


def test_the_search_ceiling_counts_this_runs_search_requests(tmp_path: Path) -> None:
    ledger = tmp_path / "L.jsonl"
    line = {"kind": "fetch", "label": "s/minimax_search.country", "batch_id": "srch-0001"}
    other = {"kind": "fetch", "label": "s/enwiki", "batch_id": "batch-0001"}
    ledger.write_text("".join(json.dumps(r) + "\n" for r in (line, other, line)), encoding="utf-8")
    spend = MR.Spend.from_ledger(ledger)
    assert (spend.searches, spend.fetch_lines) == (2, 3)
    baseline = MR.Spend(searches=1)
    assert MR.Budget(max_searches=2).stop_reason(spend, baseline=baseline) is None
    assert "search ceiling" in str(MR.Budget(max_searches=1).stop_reason(spend, baseline=baseline))


def _search_json(
    root: Path, *, failed: int = 0, stopped: str | None = None, judged: bool = False
) -> None:
    """A search batch's `search.json`; with `judged`, also every other artefact of a done batch."""
    root.mkdir(parents=True, exist_ok=True)
    (root / "input.json").write_text("{}", encoding="utf-8")
    payload = {"quota": [{"before": {"weekly_remains_tokens": 9}, "after": {"weekly_remains_tokens": 8},
                          "requests": 1}],
               "stopped": stopped, "totals": {"failed": failed}}  # fmt: skip
    (root / "search.json").write_text(json.dumps(payload), encoding="utf-8")
    if judged:
        (root / "fetch.json").write_text("{}", encoding="utf-8")
        model = {"totals": {"calls": 0}, "judgements": [], "failures": []}
        (root / "model.json").write_text(json.dumps(model), encoding="utf-8")


def test_a_batch_whose_search_is_incomplete_is_never_done(tmp_path: Path) -> None:
    """Every other artefact says done; only the incomplete search keeps the batch from it."""
    _search_json(tmp_path / "srch-0000", judged=True)
    assert MR.batch_state(tmp_path, "srch-0000")[0] == MR.DONE
    _search_json(tmp_path / "srch-0001", failed=1, judged=True)
    assert MR.batch_state(tmp_path, "srch-0001")[0] == MR.PARTIAL
    _search_json(tmp_path / "srch-0002", stopped="quota", judged=True)
    assert MR.batch_state(tmp_path, "srch-0002")[0] == MR.PARTIAL
    _search_json(tmp_path / "srch-0003", judged=True)
    (tmp_path / "srch-0003" / "search.json").write_text("{", encoding="utf-8")
    assert MR.batch_state(tmp_path, "srch-0003")[0] == MR.BROKEN
    # A report without its verdict fields is not a clean one.
    for payload in (
        {"totals": {"failed": 0}},
        {"stopped": None},
        {"stopped": None, "totals": {"failed": "0"}},
    ):
        _search_json(tmp_path / "srch-0004", judged=True)
        (tmp_path / "srch-0004" / "search.json").write_text(json.dumps(payload), encoding="utf-8")
        assert MR.batch_state(tmp_path, "srch-0004")[0] == MR.BROKEN, payload


@pytest.mark.parametrize("done_before", [False, True])
def test_the_progress_file_carries_each_search_batchs_quota_readings(
    tmp_path: Path, done_before: bool
) -> None:
    """Also for a batch this run skips as done: a resumed run starts a fresh progress file, and the
    readings an earlier run took must be in it (they are the plan's only cost signal)."""
    run_dir = tmp_path / "runs"
    _search_json(run_dir / "srch-0001", judged=done_before)
    ran: list[str] = []

    class Stub:
        spawn_retries = 0

        def __init__(self) -> None:
            self.run_dir = run_dir

        def batch(self, planned: MR.PlannedBatch) -> tuple[bool, str]:
            ran.append(planned.batch_id)
            return True, "done"

    progress = MR.Progress(plan="p", run_dir=str(run_dir), live=True, jobs=1, batches_total=1)
    MR.run_mass(
        batches=[MR.PlannedBatch("srch-0001", 1, 1, 1, 1)],
        runner=Stub(),
        budget=MR.Budget(),
        ledger=tmp_path / "L.jsonl",
        progress=progress,
        progress_path=tmp_path / "progress.json",
        jobs=1,
    )
    assert ran == ([] if done_before else ["srch-0001"])
    written = json.loads((tmp_path / "progress.json").read_text(encoding="utf-8"))
    (entry,) = written["quota"]["srch-0001"]
    assert entry["before"]["weekly_remains_tokens"] == 9
    assert entry["after"]["weekly_remains_tokens"] == 8


def test_a_damaged_search_report_stops_the_driver_before_it_starts(tmp_path: Path) -> None:
    run_dir = tmp_path / "runs"
    _search_json(run_dir / "srch-0001")
    (run_dir / "srch-0001" / "search.json").write_text(json.dumps({"quota": {}}), encoding="utf-8")
    progress = MR.Progress(plan="p", run_dir=str(run_dir), live=True, jobs=1, batches_total=1)
    runner = types.SimpleNamespace(run_dir=run_dir, spawn_retries=0, batch=None)
    with pytest.raises(R.InputError, match="quota"):
        MR.run_mass(
            batches=[MR.PlannedBatch("srch-0001", 1, 1, 1, 1)],
            runner=runner,
            budget=MR.Budget(),
            ledger=tmp_path / "L.jsonl",
            progress=progress,
            progress_path=tmp_path / "progress.json",
            jobs=1,
        )
