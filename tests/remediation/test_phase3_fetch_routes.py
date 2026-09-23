"""The 2026-09-22 additions to the fetch stage: a cut page says so, the narrowed Wikidata route, and
the English article through the item's own sitelink (W12).

All three exist for new runs only (the gap run of the 152 over-bound sites), so the first group of tests
pins that a record which asks for nothing new buys exactly the targets it always bought. No test here
opens a socket: every answer is a fixture shaped like the live answer measured on 2026-09-22 (Q37200,
the Great Pyramid of Giza, through WDQS and `wbgetclaims`).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlsplit

import httpx
import pytest

REPO = Path(__file__).resolve().parents[2]
PHASE3_PARENT = REPO / "scripts" / "remediation"
if str(PHASE3_PARENT) not in sys.path:
    sys.path.insert(0, str(PHASE3_PARENT))

from phase3 import discover_stage as DS  # noqa: E402
from phase3 import fetch_stage as F  # noqa: E402
from phase3 import ledger as L  # noqa: E402
from phase3 import model_stage as MS  # noqa: E402
from phase3 import snapshot_plan as SP  # noqa: E402
from phase3.model import Stage  # noqa: E402
from phase3.run import InputError  # noqa: E402

SITE = "5f0c1a3e-0000-4000-8000-000000000001"
QID = "Q37200"

#: The live WDQS answer's shape for Q37200 (2026-09-22), trimmed to one value per kind.
TRUTHY_ANSWER = {
    "head": {"vars": ["property", "value", "valueLabel"]},
    "results": {
        "bindings": [
            {
                "value": {"type": "uri", "value": "http://www.wikidata.org/entity/Q381885"},
                "valueLabel": {"xml:lang": "en", "type": "literal", "value": "tomb"},
                "property": {"type": "uri", "value": "http://www.wikidata.org/entity/P31"},
            },
            {
                "value": {"xml:lang": "en", "type": "literal", "value": "Great Pyramid of Giza"},
                "property": {"type": "literal", "value": "label"},
            },
            {
                "value": {"type": "uri", "value": "http://www.wikidata.org/entity/Q79"},
                "valueLabel": {"xml:lang": "en", "type": "literal", "value": "Egypt"},
                "property": {"type": "uri", "value": "http://www.wikidata.org/entity/P17"},
            },
            {
                "property": {"type": "uri", "value": "http://www.wikidata.org/entity/P625"},
                "value": {
                    "datatype": "http://www.opengis.net/ont/geosparql#wktLiteral",
                    "type": "literal",
                    "value": "Point(31.13422 29.97915)",
                },
            },
            {
                "value": {"type": "uri", "value": "http://www.wikidata.org/entity/Q839954"},
                "valueLabel": {"xml:lang": "en", "type": "literal", "value": "archaeological site"},
                "property": {"type": "uri", "value": "http://www.wikidata.org/entity/P31"},
            },
            {
                "value": {"xml:lang": "en", "type": "literal", "value": "oldest pyramid at Giza"},
                "property": {"type": "literal", "value": "description"},
            },
        ]
    },
}

#: The live `wbgetclaims` answer for Q37200 P571 (2026-09-22), its reference kept: it is what the
#: rendering must leave out.
P571_ANSWER = {
    "claims": {
        "P571": [
            {
                "mainsnak": {
                    "snaktype": "value",
                    "property": "P571",
                    "datavalue": {
                        "value": {
                            "time": "-2560-00-00T00:00:00Z",
                            "timezone": 0,
                            "before": 0,
                            "after": 0,
                            "precision": 9,
                            "calendarmodel": "http://www.wikidata.org/entity/Q1985786",
                        },
                        "type": "time",
                    },
                    "datatype": "time",
                },
                "type": "statement",
                "qualifiers": {
                    "P1480": [
                        {
                            "snaktype": "value",
                            "property": "P1480",
                            "datavalue": {
                                "value": {"entity-type": "item", "id": "Q5727902"},
                                "type": "wikibase-entityid",
                            },
                        }
                    ]
                },
                "rank": "normal",
                "references": [{"snaks": {"P304": [{"datavalue": {"value": "160"}}]}}],
            }
        ]
    }
}


def _record(**extra: Any) -> dict[str, Any]:
    record: dict[str, Any] = {
        "site_id": SITE,
        "name": "Great Pyramid of Giza",
        "findings": [SP.finding_row(field, "a value") for field in SP.DISCOVER_FIELDS],
        "wikidata_qid": QID,
    }
    record.update(extra)
    return record


def _answer_for(url: str) -> bytes:
    """The fixture answer a narrowed-route URL gets. Anything else is a request nobody planned."""
    parts = urlsplit(url)
    query = parse_qs(parts.query)
    if parts.netloc == "query.wikidata.org":
        return json.dumps(TRUTHY_ANSWER).encode("utf-8")
    if query.get("action") == ["wbgetclaims"]:
        pid = query["property"][0]
        return json.dumps(P571_ANSWER if pid == "P571" else {"claims": {}}).encode("utf-8")
    if parts.netloc == "en.wikipedia.org":
        return json.dumps(
            {"query": {"pages": {"1": {"extract": "It was built c. 2560 BC."}}}}
        ).encode()
    raise AssertionError(f"unplanned request {url}")


def _collect(tmp_path: Path, record: dict[str, Any], handler: Any) -> tuple[Any, F.EvidenceStore]:
    store = F.EvidenceStore(tmp_path / "evidence")
    with F.HttpFetcher(transport=httpx.MockTransport(handler)) as fetcher:
        report = F.collect_batch(
            batch={"batch_id": "gap-0001", "sites": [record]},
            fetcher=fetcher,
            store=store,
            ledger=L.Ledger(tmp_path / "LEDGER.jsonl"),
            stage=Stage.FINDER,
            sleep=lambda _seconds: None,
        )
    return report, store


def _handler(request: httpx.Request) -> httpx.Response:
    if urlsplit(str(request.url)).path == "/":
        return httpx.Response(200, content=b"root")  # the host probe
    return httpx.Response(200, content=_answer_for(str(request.url)))


# ── nothing changes for a record that asks for nothing new ─────────────────────────────────────


def test_a_record_without_a_route_key_buys_exactly_the_old_two_targets() -> None:
    targets = F.targets_for_site(_record())
    assert [t.feature for t in targets] == [F.FEATURE_ENWIKI, F.FEATURE_WIKIDATA_ENTITY]
    assert all(t.qid is None for t in targets)


# ── a cut page says so ─────────────────────────────────────────────────────────────────────────


def test_a_page_cut_at_the_cap_is_stored_with_the_truncation_marker(tmp_path: Path) -> None:
    """27 judged sites of the mass run were shown a cut page with nothing saying it was cut."""
    record = _record()
    del record["wikidata_qid"]

    def handler(request: httpx.Request) -> httpx.Response:
        if urlsplit(str(request.url)).path == "/":
            return httpx.Response(200, content=b"root")
        return httpx.Response(200, content=b"a" * (F.MAX_PAGE_BYTES + 5000))

    report, store = _collect(tmp_path, record, handler)
    text = store.path_for(SITE, F.FEATURE_ENWIKI).read_text(encoding="utf-8")
    assert text.endswith(F.TRUNCATION_MARKER)
    assert text[: F.MAX_PAGE_BYTES] == "a" * F.MAX_PAGE_BYTES
    assert "61,440-byte page cap" in F.TRUNCATION_MARKER
    outcome = json.loads(report.to_json())["sites"][0]["outcomes"][0]
    assert outcome["truncated"] is True and outcome["attempts"][0]["bytes"] == F.MAX_PAGE_BYTES


def test_a_page_below_the_cap_carries_no_marker(tmp_path: Path) -> None:
    record = _record()
    del record["wikidata_qid"]
    report, store = _collect(tmp_path, record, _handler)
    text = store.path_for(SITE, F.FEATURE_ENWIKI).read_text(encoding="utf-8")
    assert "[truncated:" not in text
    assert json.loads(report.to_json())["sites"][0]["outcomes"][0]["truncated"] is False


def test_a_cut_through_a_character_leaves_a_file_the_judge_can_read(tmp_path: Path) -> None:
    """`é` is two bytes; a cut after an odd number of bytes splits one, and the judge reads UTF-8."""
    record = _record()
    del record["wikidata_qid"]

    def handler(request: httpx.Request) -> httpx.Response:
        if urlsplit(str(request.url)).path == "/":
            return httpx.Response(200, content=b"root")
        return httpx.Response(200, content=b"x" + "é".encode() * F.MAX_PAGE_BYTES)

    _, store = _collect(tmp_path, record, handler)
    # read as the judge reads it: this raises if half a character was kept before the marker
    text = store.path_for(SITE, F.FEATURE_ENWIKI).read_text(encoding="utf-8")
    assert text.endswith(F.TRUNCATION_MARKER)
    assert text.startswith("xé")


# ── the narrowed Wikidata route ──────────────────────────────────────────────────────────────


def test_the_narrow_route_replaces_the_full_entity_with_the_five_narrow_targets() -> None:
    targets = F.targets_for_site(_record(wikidata_route="narrow"))
    assert [t.feature for t in targets] == [
        F.FEATURE_ENWIKI,
        F.FEATURE_WIKIDATA_TRUTHY,
        "wikidata_claims.P571",
        "wikidata_claims.P580",
        "wikidata_claims.P582",
        "wikidata_claims.P1619",
    ]
    assert all(t.qid == QID for t in targets[1:]) and targets[0].qid is None
    for target in targets:
        F.assert_named_feature(target.url)
    assert "props=claims" not in " ".join(t.url for t in targets)
    claims = [parse_qs(urlsplit(t.url).query) for t in targets[2:]]
    assert [q["property"] for q in claims] == [["P571"], ["P580"], ["P582"], ["P1619"]]
    assert all(q["action"] == ["wbgetclaims"] and q["entity"] == [QID] for q in claims)


def test_no_date_is_read_through_wdqs() -> None:
    """WDQS turns the API's -2560 into -2559 (a year 0) and Julian 537-12-27 into 537-12-29."""
    query = F.wikidata_truthy_query(QID)
    for pid in F.DATE_PROPERTIES:
        assert f"wd:{pid} " not in query and f"wd:{pid}}}" not in query, pid
    for pid in F.TRUTHY_PROPERTIES:
        assert f"wd:{pid}" in query
    assert "wikibase:BestRank" in query and f"wd:{QID}" in query
    url = F.wikidata_truthy_url(QID)
    assert url.startswith(F.WDQS_ENDPOINT + "?") and unquote(url).endswith("format=json")


def test_the_truthy_query_names_every_predicate_instead_of_scanning_a_variable_one() -> None:
    """Q99151: the variable-predicate form took 20.0 s on WDQS, the explicit one 0.3 s."""
    query = F.wikidata_truthy_query(QID)
    assert "?claim" not in query and "wikibase:claim" not in query
    for pid in F.TRUTHY_PROPERTIES:
        assert f"p:{pid} ?statement" in query and f"ps:{pid} ?value" in query
    for pid in F.DATE_PROPERTIES:
        assert f"p:{pid} " not in query


class _Clock:
    """One timeline for the pacer's clock and sleeper, so the wait is asserted, not slept."""

    def __init__(self) -> None:
        self.now = 1000.0
        self.slept: list[float] = []

    def time(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now += seconds


def test_wdqs_is_asked_at_most_once_a_second_and_other_hosts_at_the_default_pace(
    tmp_path: Path,
) -> None:
    """WDQS answered 429 with Retry-After: 120 seven times at the default pace (2026-09-22)."""
    clock = _Clock()
    pacer = F.HostPacer(tmp_path / "pacing", clock=clock.time, sleep=clock.sleep)
    assert pacer.wait("query.wikidata.org") == 0.0
    assert pacer.wait("query.wikidata.org") == pytest.approx(1.0)
    assert pacer.wait("www.wikidata.org") == 0.0
    assert pacer.wait("www.wikidata.org") == pytest.approx(F.HOST_MIN_INTERVAL_SECONDS)
    assert F.HOST_MIN_INTERVAL_OVERRIDES == {"query.wikidata.org": 1.0}


def test_a_misspelt_or_unanchored_route_is_refused_not_ignored() -> None:
    with pytest.raises(InputError, match="the one route this stage knows"):
        F.targets_for_site(_record(wikidata_route="narrowed"))
    record = _record(wikidata_route="narrow")
    del record["wikidata_qid"]
    with pytest.raises(InputError, match="without a wikidata_qid"):
        F.targets_for_site(record)
    with pytest.raises(InputError, match="is not a Q-number"):
        F.wikidata_claims_url("Q1 OR 1=1", "P571")
    with pytest.raises(InputError, match="time-valued"):
        F.wikidata_claims_url(QID, "P31")


def test_the_truthy_answer_renders_one_sorted_line_per_value_and_names_the_absent() -> None:
    text = F.render_truthy(QID, json.dumps(TRUTHY_ANSWER).encode())
    assert text.splitlines() == [
        f"Wikidata item {QID}, read through the Wikidata Query Service: its English label and "
        "description, and the best-rank values of P31, P17, P131, P2348, P625.",
        "label (en): Great Pyramid of Giza",
        "description (en): oldest pyramid at Giza",
        "P31 instance of: Q381885 tomb",
        "P31 instance of: Q839954 archaeological site",
        "P17 country: Q79 Egypt",
        "P131 located in the administrative territorial entity: none",
        "P2348 time period: none",
        "P625 coordinate location: Point(31.13422 29.97915)",
    ]
    reordered = dict(TRUTHY_ANSWER)
    reordered["results"] = {"bindings": TRUTHY_ANSWER["results"]["bindings"][::-1]}
    assert F.render_truthy(QID, json.dumps(reordered).encode()) == text


def test_a_truthy_answer_that_is_not_the_asked_shape_is_refused() -> None:
    with pytest.raises(F.EvidenceUnrenderable, match="not JSON"):
        F.render_truthy(QID, b"java.util.concurrent.TimeoutException")
    with pytest.raises(F.EvidenceUnrenderable, match="results.bindings"):
        F.render_truthy(QID, b"{}")
    stray = {
        "results": {
            "bindings": [
                {
                    "property": {"type": "uri", "value": "http://www.wikidata.org/entity/P571"},
                    "value": {"type": "literal", "value": "-2559-01-01T00:00:00Z"},
                }
            ]
        }
    }
    with pytest.raises(F.EvidenceUnrenderable, match="nobody asked for"):
        F.render_truthy(QID, json.dumps(stray).encode())


def test_a_date_renders_as_the_api_states_it_with_precision_calendar_rank_and_circa() -> None:
    text = F.render_claims(QID, "P571", json.dumps(P571_ANSWER).encode())
    assert text.splitlines() == [
        f"Wikidata item {QID}, property P571 inception, read through the Wikidata API "
        "(wbgetclaims), every statement with its rank; references are not shown.",
        "P571 inception: -2560-00-00T00:00:00Z (precision 9 = year, proleptic Julian calendar) "
        "(rank normal)",
        "  qualifier P1480 sourcing circumstances: Q5727902 circa",
    ]
    assert "P304" not in text and "160" not in text  # the reference is not evidence text
    empty = F.render_claims(QID, "P580", b'{"claims":{}}')
    assert empty.splitlines()[-1] == "P580 start time: none"
    with pytest.raises(F.EvidenceUnrenderable, match="claims other than P580"):
        F.render_claims(QID, "P580", json.dumps(P571_ANSWER).encode())
    with pytest.raises(F.EvidenceUnrenderable, match="no `claims`"):
        F.render_claims(QID, "P571", b'{"error": {"code": "no-such-entity"}}')


def test_the_narrow_route_stores_renderings_and_keeps_the_bytes_read(tmp_path: Path) -> None:
    report, store = _collect(tmp_path, _record(wikidata_route="narrow"), _handler)
    assert report.failed == []
    rendered = store.path_for(SITE, F.FEATURE_WIKIDATA_TRUTHY).read_text(encoding="utf-8")
    assert rendered == F.render_truthy(QID, json.dumps(TRUTHY_ANSWER).encode())
    raw = store.raw_path_for(SITE, F.FEATURE_WIKIDATA_TRUTHY)
    assert raw.parent.name == F.RAW_EVIDENCE_DIR and raw.parent.parent == tmp_path
    assert json.loads(raw.read_bytes()) == TRUTHY_ANSWER
    date = store.path_for(SITE, "wikidata_claims.P571").read_text(encoding="utf-8")
    assert "-2560-00-00T00:00:00Z" in date


def test_the_finder_and_the_citation_check_read_the_rendering(tmp_path: Path) -> None:
    """What the prompt shows is what a quote is checked against: a rendered line is quotable."""
    record = _record(wikidata_route="narrow")
    _collect(tmp_path, record, _handler)
    excerpts = MS.evidence_excerpts(
        site_id=SITE, site=record, store=F.EvidenceStore(tmp_path / "evidence"), hit_pages=False
    )
    pages = DS.pages_from_excerpts(excerpts)
    assert len(pages) == 6
    claims_url = F.wikidata_claims_url(QID, "P571")
    quote = "P571 inception: -2560-00-00T00:00:00Z (precision 9 = year, proleptic Julian calendar)"
    answer = DS.parse_answer(
        "The item states 2560 BC.\n"
        "PROPOSED: -2560\n"
        f'SOURCE: {claims_url} - "{quote}"\n'
        "VERDICT: WRONG\n"
    )
    assert DS.source_problems(answer, pages) == ()
    MS.check_evidence_bound(SITE, excerpts)  # the narrowed evidence is a few hundred characters
    assert sum(excerpt.chars for excerpt in excerpts) < 3000


def _cite(url: str, quote: str) -> DS.DiscoverAnswer:
    return DS.parse_answer(
        f'The item is a tomb.\nPROPOSED: Tomb\nSOURCE: {url} - "{quote}"\nVERDICT: WRONG\n'
    )


def test_a_truthy_line_is_cited_through_the_short_address_the_prompt_shows(tmp_path: Path) -> None:
    """The WDQS GET address is ~2 KB of percent-encoding and a citation is matched byte for byte.

    `site_type` and `country` corrections rest on the P31/P17 lines; a finder that had to re-type
    the query URL exactly would lose them to one slipped character. So the prompt shows - and the
    citation check keys the page by - the item's own page, while the fetch still asks WDQS.
    """
    asked: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        asked.append(str(request.url))
        return _handler(request)

    record = _record(wikidata_route="narrow")
    report, _ = _collect(tmp_path, record, handler)
    truthy = next(t for t in F.targets_for_site(record) if t.feature == F.FEATURE_WIKIDATA_TRUTHY)
    assert truthy.url == f"https://www.wikidata.org/wiki/{QID}#{F.FEATURE_WIKIDATA_TRUTHY}"
    assert truthy.request_url == F.wikidata_truthy_url(QID) and len(truthy.request_url) > 1000
    assert truthy.request_url in asked and truthy.url not in asked  # WDQS is what is asked
    # the fetch report records what was requested, and names both addresses for the target
    site = json.loads(report.to_json())["sites"][0]
    outcome = next(o for o in site["outcomes"] if o["feature"] == F.FEATURE_WIKIDATA_TRUTHY)
    assert outcome["url"] == truthy.request_url
    listed = next(t for t in site["targets"] if t["feature"] == F.FEATURE_WIKIDATA_TRUTHY)
    assert (listed["url"], listed["request_url"]) == (truthy.url, truthy.request_url)
    # the prompt shows the short address, and a P31 line cited through it passes the check
    excerpts = MS.evidence_excerpts(
        site_id=SITE, site=record, store=F.EvidenceStore(tmp_path / "evidence"), hit_pages=False
    )
    shown = next(e for e in excerpts if e.feature == F.FEATURE_WIKIDATA_TRUTHY)
    assert shown.url == truthy.url
    assert f'url="{truthy.url}"' in MS.evidence_block(excerpts)
    pages = DS.pages_from_excerpts(excerpts)
    line = "P31 instance of: Q381885 tomb"
    assert DS.source_problems(_cite(truthy.url, line), pages) == ()
    assert DS.source_problems(_cite(truthy.url, "P31 instance of: Q1 fortress"), pages)
    # a record without the route still shows and asks one and the same address per target
    plain = F.targets_for_site(_record())
    assert all(t.query_url is None and t.request_url == t.url for t in plain)


def test_the_truthy_addresses_refuse_a_qid_that_is_not_a_q_number() -> None:
    for build in (F.wikidata_truthy_url, F.wikidata_truthy_citation_url, F.wikidata_truthy_query):
        with pytest.raises(InputError, match="is not a Q-number"):
            build("Q1 } UNION { ?s ?p ?o")


def test_a_rendered_answer_that_hit_the_cap_is_refused_not_rendered(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if urlsplit(str(request.url)).path == "/":
            return httpx.Response(200, content=b"root")
        if "query.wikidata.org" in str(request.url):
            return httpx.Response(200, content=b"{" + b" " * F.MAX_PAGE_BYTES)
        return httpx.Response(200, content=_answer_for(str(request.url)))

    with pytest.raises(F.EvidenceUnrenderable, match="hit the 61440-byte cap"):
        _collect(tmp_path, _record(wikidata_route="narrow"), handler)


# ── the English article through the item's sitelink (W12) ─────────────────────────────────────


def test_a_resolved_sitelink_adds_the_items_article_after_the_name_route() -> None:
    record = _record(name="Larisa Argos", enwiki_sitelink={"qid": QID, "title": "Larisa (Argos)"})
    targets = F.targets_for_site(record)
    assert [t.feature for t in targets] == [
        F.FEATURE_ENWIKI,
        F.FEATURE_ENWIKI_SITELINK,
        F.FEATURE_WIKIDATA_ENTITY,
    ]
    assert targets[1].url == F.wikipedia_extract_url("Larisa (Argos)")


def test_a_sitelink_for_another_item_or_the_same_title_or_a_bad_shape_is_refused() -> None:
    with pytest.raises(InputError, match="stale resolution"):
        F.targets_for_site(_record(enwiki_sitelink={"qid": "Q1", "title": "Somewhere"}))
    with pytest.raises(InputError, match="already fetches that article"):
        F.targets_for_site(_record(enwiki_sitelink={"qid": QID, "title": "Great Pyramid of Giza"}))
    with pytest.raises(InputError, match="not \\{qid, title\\}"):
        F.targets_for_site(_record(enwiki_sitelink="Larisa (Argos)"))
    with pytest.raises(InputError, match="carries no title"):
        F.targets_for_site(_record(enwiki_sitelink={"qid": QID, "title": " "}))


class _Recorder:
    """A `Fetcher` that answers from a table and remembers every URL it was asked."""

    def __init__(self, answers: dict[str, dict[str, Any]], status: int = 200) -> None:
        self.answers = answers
        self.status = status
        self.asked: list[str] = []

    def get(self, url: str) -> F.FetchedPage:
        self.asked.append(url)
        ids = parse_qs(urlsplit(url).query)["ids"][0].split("|")
        body = {"entities": {qid: self.answers[qid] for qid in ids}}
        return F.FetchedPage(
            status=self.status, final_url=url, body=json.dumps(body).encode(), truncated=False
        )


def test_a_shared_item_is_refused_without_a_request_and_the_rest_are_resolved() -> None:
    """212 sites share 90 items; 'Dolmens of Sardinia' links 'Dolmen', which is no one site."""
    fetcher = _Recorder(
        {
            "Q10": {
                "sitelinks": {"enwiki": {"site": "enwiki", "title": "Larisa (Argos)", "badges": []}}
            },
            "Q11": {"sitelinks": {}},
        }
    )
    resolved = F.resolve_enwiki_sitelinks(
        {"site-a": "Q10", "site-b": "Q11", "site-c": "Q309", "site-d": "Q309"},
        shared={"Q10": 1, "Q11": 1, "Q309": 7},
        fetcher=fetcher,
    )
    assert resolved["site-a"].to_record() == {"qid": "Q10", "title": "Larisa (Argos)"}
    assert resolved["site-b"].title is None and "no English Wikipedia sitelink" in str(
        resolved["site-b"].refused
    )
    for site in ("site-c", "site-d"):
        assert resolved[site].title is None and "carried by 7 curated sites" in str(
            resolved[site].refused
        )
    assert len(fetcher.asked) == 1 and "Q309" not in fetcher.asked[0]
    with pytest.raises(InputError, match="no usable sitelink"):
        resolved["site-c"].to_record()


def test_a_failed_or_missing_lookup_stops_the_resolution() -> None:
    with pytest.raises(F.EvidenceUnrenderable, match="HTTP 503"):
        F.resolve_enwiki_sitelinks(
            {"site-a": "Q10"}, shared={}, fetcher=_Recorder({"Q10": {}}, status=503)
        )
    with pytest.raises(F.EvidenceUnrenderable, match="does not exist"):
        F.resolve_enwiki_sitelinks(
            {"site-a": "Q10"}, shared={}, fetcher=_Recorder({"Q10": {"missing": ""}})
        )


class _Fixed:
    """A `Fetcher` whose every answer is one body, whatever it was asked."""

    def __init__(self, entities: dict[str, Any], *, truncated: bool = False) -> None:
        self.body = json.dumps({"entities": entities}).encode()
        self.truncated = truncated
        self.asked: list[str] = []

    def get(self, url: str) -> F.FetchedPage:
        self.asked.append(url)
        return F.FetchedPage(status=200, final_url=url, body=self.body, truncated=self.truncated)


def _sitelink(title: str, *badges: str) -> dict[str, Any]:
    return {"sitelinks": {"enwiki": {"site": "enwiki", "title": title, "badges": list(badges)}}}


def test_a_sitelink_badged_as_a_redirect_is_refused_with_the_badge_named() -> None:
    """Q4810863 (Estipeon's item after the repair) links enwiki `Astibo`, badge Q70893996, and
    `Astibo` redirects to `Štip#History`: the extract route would judge the site on the modern town.
    """
    resolved = F.resolve_enwiki_sitelinks(
        {"estipeon": "Q4810863", "andriake": "Q510000", "other": "Q7"},
        shared={},
        fetcher=_Fixed(
            {
                "Q4810863": _sitelink("Astibo", "Q70893996"),
                "Q510000": _sitelink("Andriake"),
                "Q7": _sitelink("Somewhere", "Q70894304"),
            }
        ),
    )
    assert resolved["andriake"].to_record() == {"qid": "Q510000", "title": "Andriake"}
    for site, badge in (("estipeon", "Q70893996 sitelink to redirect"), ("other", "Q70894304")):
        refused = str(resolved[site].refused)
        assert badge in refused and "is a redirect" in refused
        with pytest.raises(InputError, match="no usable sitelink"):
            resolved[site].to_record()


def test_a_sitelink_without_its_badges_list_is_refused_not_read_as_unbadged() -> None:
    with pytest.raises(F.EvidenceUnrenderable, match="without title and badges"):
        F.resolve_enwiki_sitelinks(
            {"site-a": "Q10"},
            shared={},
            fetcher=_Fixed({"Q10": {"sitelinks": {"enwiki": {"title": "Larisa (Argos)"}}}}),
        )


def test_an_answer_that_omits_an_asked_item_or_was_cut_stops_the_resolution() -> None:
    with pytest.raises(F.EvidenceUnrenderable, match="Q11: asked for, and absent"):
        F.resolve_enwiki_sitelinks(
            {"site-a": "Q10", "site-b": "Q11"},
            shared={},
            fetcher=_Fixed({"Q10": _sitelink("Larisa (Argos)")}),
        )
    with pytest.raises(F.EvidenceUnrenderable, match="truncated=True"):
        F.resolve_enwiki_sitelinks(
            {"site-a": "Q10"},
            shared={},
            fetcher=_Fixed({"Q10": _sitelink("Larisa (Argos)")}, truncated=True),
        )


def test_the_sitelinks_request_takes_one_to_fifty_items() -> None:
    assert "ids=Q1%7CQ2" in F.wikidata_sitelinks_url(["Q1", "Q2"])
    F.wikidata_sitelinks_url([f"Q{n}" for n in range(1, 51)])
    for count in (0, 51):
        with pytest.raises(InputError, match="1 to 50 per request"):
            F.wikidata_sitelinks_url([f"Q{n}" for n in range(1, count + 1)])


def test_a_resolution_with_a_title_and_a_refusal_has_no_record() -> None:
    """A redirect keeps its title for the report, and still gives the plan nothing to route by."""
    both = F.SitelinkResolution(qid="Q1", title="Astibo", refused="a redirect")
    with pytest.raises(InputError, match="no usable sitelink \\(a redirect\\)"):
        both.to_record()


def test_a_sitelink_record_with_an_extra_key_is_refused() -> None:
    with pytest.raises(InputError, match="not \\{qid, title\\}"):
        F.targets_for_site(
            _record(enwiki_sitelink={"qid": QID, "title": "Giza pyramid complex", "badges": []})
        )
