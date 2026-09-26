"""The shared field harvest (`scripts/remediation/fields/harvest.py`): the files WD1 and WD2 read.

DB-less and offline: production is a fake reader, the web an `httpx.MockTransport` behind the
harvest's own clients. What is pinned: the SITES.jsonl contract, the sample, resumability (a file is
fetched once), a merged item, the source-URL records of every kind, and the transport that carries
the plain User-Agent past Wikimedia's and UNESCO's refusal of httpx's own handshake.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import httpx
import pytest
import requests

REPO = Path(__file__).resolve().parents[2]
if str(REPO / "scripts" / "remediation") not in sys.path:
    sys.path.insert(0, str(REPO / "scripts" / "remediation"))

from census.fetch import Fetcher  # noqa: E402
from fields import harvest as H  # noqa: E402
from fields import transport as T  # noqa: E402

A_ID = "0025b0ba-fd74-4c08-96e3-acc17956aa44"
B_ID = "786cada5-1feb-4c5c-9e79-b8ffdf8aacc6"
C_ID = "99a98235-0000-4000-8000-000000000003"


def row(site_id: str, **over: Any) -> dict[str, Any]:
    base = {
        "site_id": site_id,
        "name": "Stonehenge",
        "country": "England",
        "lat": 51.178844,
        "lon": -1.826189,
        "qid": "Q39671",
        "enwiki_title": "Stonehenge",
        "source_url": "https://en.wikipedia.org/wiki/Stonehenge",
        "scope_status": None,
    }
    base.update(over)
    return base


class TestTheSites:
    def test_a_line_is_exactly_the_contract(self) -> None:
        line = H.site_line(row(A_ID))
        assert tuple(line) == H.SITE_KEYS
        assert H.site_line(row(A_ID, qid=None))["qid"] is None

    def test_an_item_id_that_is_not_one_is_refused(self) -> None:
        with pytest.raises(H.HarvestError, match="is not a Wikidata item id"):
            H.site_line(row(A_ID, qid="P31"))

    def test_the_export_writes_every_curated_site_in_id_order(self, tmp_path: Path) -> None:
        rows = [row(B_ID), row(A_ID, scope_status="retired")]
        result = H.export(tmp_path, reader=lambda sql: rows)
        assert result == {"sites": 2, "curated": 2, "retired": 1, "with_qid": 2}
        assert [s["site_id"] for s in H.read_sites(tmp_path)] == [A_ID, B_ID]
        meta = json.loads((tmp_path / H.META_FILE).read_text(encoding="utf-8"))
        assert meta["user_agent"] == "AncientMapRemediation/1.0 (research)"
        assert meta["sample"] is None and "site_external_ids" in meta["sql"]

    def test_an_empty_export_is_refused(self, tmp_path: Path) -> None:
        with pytest.raises(H.HarvestError, match="no curated site"):
            H.export(tmp_path, reader=lambda sql: [])

    def test_a_sample_is_reproducible_and_never_retired(self, tmp_path: Path) -> None:
        rows = [row(A_ID), row(B_ID, scope_status="retired"), row(C_ID)]
        first = H.choose_sample(rows, 2, seed=7)
        assert first == H.choose_sample(rows, 2, seed=7)
        assert B_ID not in first
        with pytest.raises(H.HarvestError, match="a sample of 3 from 2"):
            H.choose_sample(rows, 3, seed=7)
        H.export(tmp_path, reader=lambda sql: rows, sample=1, seed=3)
        assert len(H.read_sites(tmp_path)) == 1

    def test_a_line_with_other_keys_is_refused(self, tmp_path: Path) -> None:
        (tmp_path / H.SITES_FILE).write_text(json.dumps({"site_id": A_ID}) + "\n", encoding="utf-8")
        with pytest.raises(H.HarvestError, match="not"):
            H.read_sites(tmp_path)


# ------------------------------------------------------------------------------ the web, faked
def wikidata(request: httpx.Request) -> httpx.Response:
    params = dict(request.url.params)
    ids = params["ids"].split("|")
    entities: dict[str, Any] = {}
    for qid in ids:
        if qid == "Q1":  # merged into Q2: answered under the target, `redirects.from` names it
            entities["Q2"] = {"id": "Q2", "redirects": {"from": "Q1", "to": "Q2"}, "claims": {}}
            continue
        entities[qid] = {
            "id": qid,
            "claims": {
                "P31": [
                    {
                        "rank": "normal",
                        "mainsnak": {"datavalue": {"value": {"id": "Q839954"}}},
                    }
                ]
            },
            "sitelinks": {"enwiki": {"title": "Stonehenge"}},
            "labels": {"en": {"value": "archaeological site"}},
        }
    return httpx.Response(200, json={"entities": entities})


def enwiki(request: httpx.Request) -> httpx.Response:
    params = dict(request.url.params)
    titles = params["titles"].split("|")
    if params.get("prop") == "coordinates|pageprops":
        pages = [
            {"title": t, "coordinates": [{"lat": 51.1789, "lon": -1.8262, "globe": "earth"}],
             "pageprops": {"wikibase_item": "Q39671"}}
            for t in titles
        ]  # fmt: skip
        return httpx.Response(200, json={"query": {"pages": pages}})
    redirects = [{"from": "Old Sarum Castle", "to": "Old Sarum", "tofragment": "Castle"}]
    pages = []
    for t in titles:
        if t == "Nowhere":
            pages.append({"title": t, "missing": True})
        elif t == "Old Sarum Castle":
            continue
        else:
            pages.append({"title": t, "pageprops": {"wikibase_item": "Q39671"}})
    if "Old Sarum Castle" in titles:
        pages.append({"title": "Old Sarum", "pageprops": {"wikibase_item": "Q1146418"}})
    return httpx.Response(200, json={"query": {"redirects": redirects, "pages": pages}})


def web(request: httpx.Request) -> httpx.Response:
    if request.url.path == "/moved":
        return httpx.Response(301, headers={"Location": "https://heritage.example/other"})
    if request.url.path == "/gone":
        return httpx.Response(404)
    return httpx.Response(
        200,
        headers={"Content-Type": "text/html; charset=utf-8"},
        content=b"<html><head><title>Stonehenge &amp; Avebury\n</title></head><body>x</body></html>",
    )


def router(calls: list[str]) -> httpx.MockTransport:
    def handle(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        host = request.url.host
        if host == "www.wikidata.org":
            return wikidata(request)
        if host.endswith("wikipedia.org"):
            return enwiki(request)
        return web(request)

    return httpx.MockTransport(handle)


def fetcher(tmp_path: Path, calls: list[str]) -> Fetcher:
    return Fetcher(tmp_path / "cache", workers=1, transport=router(calls), user_agent=H.USER_AGENT)


class TestTheFetch:
    def test_every_step_writes_its_files_once(self, tmp_path: Path) -> None:
        rows = [
            row(A_ID),
            row(B_ID, qid="Q1", source_url="https://en.wikipedia.org/wiki/Old_Sarum_Castle"),
            row(C_ID, qid=None, source_url="https://heritage.example/gone"),
        ]
        H.export(tmp_path, reader=lambda sql: rows)
        calls: list[str] = []
        client = httpx.Client(transport=router(calls), follow_redirects=True)
        with fetcher(tmp_path, calls) as net:
            result = H.fetch(tmp_path, net=net, client=client, sleep=lambda s: None)
        assert result["entities"] == {"items": 2, "fetched": 2, "cached": 0}
        merged = H.load_entity(tmp_path, "Q1")
        assert merged["redirects"] == {"from": "Q1", "to": "Q2"}
        assert H.load_enwiki(tmp_path, "Q39671") is not None
        assert H.load_enwiki(tmp_path, "Q39671")["lat"] == 51.1789
        sites = {s["site_id"]: s for s in H.read_sites(tmp_path)}
        section = H.load_url(tmp_path, sites[B_ID])
        assert section["redirected"] and section["fragment"] == "Castle"
        assert section["resolved_title"] == "Old Sarum"
        assert H.load_url(tmp_path, sites[C_ID])["status"] == 404
        classes = json.loads((tmp_path / H.CLASSES_FILE).read_text(encoding="utf-8"))
        assert classes["Q839954"]["label"] == "archaeological site"
        before = len(calls)
        with fetcher(tmp_path, calls) as net:
            again = H.fetch(tmp_path, net=net, client=client, sleep=lambda s: None)
        assert again["entities"]["fetched"] == 0 and again["urls"]["asked"] == 0
        assert len(calls) == before
        steps = json.loads((tmp_path / H.META_FILE).read_text(encoding="utf-8"))["steps"]
        assert set(steps) == {"entities", "classes", "enwiki", "urls"}
        assert H.status(tmp_path)["entities_harvested"] == 2

    def test_an_item_the_api_does_not_answer_stops_the_run(self) -> None:
        with pytest.raises(H.HarvestError, match="did not answer for Q5"):
            H._answered(["Q5"], {"Q6": {"id": "Q6"}})

    def test_a_failed_page_is_asked_again_only_on_request(self, tmp_path: Path) -> None:
        rows = [row(A_ID, qid=None, source_url="https://heritage.example/page")]
        H.export(tmp_path, reader=lambda sql: rows)
        H.url_path(tmp_path, A_ID).parent.mkdir(parents=True)
        H._write_json(
            H.url_path(tmp_path, A_ID),
            {"site_id": A_ID, "source_url": rows[0]["source_url"], "kind": H.URL_WEB,
             "status": None, "error": "ConnectError: x"},
        )  # fmt: skip
        calls: list[str] = []
        client = httpx.Client(transport=router(calls), follow_redirects=True)
        with fetcher(tmp_path, calls) as net:
            assert H.fetch_urls(net, client, tmp_path, H.read_sites(tmp_path))["asked"] == 0
            result = H.fetch_urls(
                net, client, tmp_path, H.read_sites(tmp_path), refetch_failed=True,
                sleep=lambda s: None,
            )  # fmt: skip
        assert result["asked"] == 1
        record = H.load_url(tmp_path, H.read_sites(tmp_path)[0])
        assert record["status"] == 200 and record["page_title"] == "Stonehenge & Avebury"

    def test_a_record_of_another_url_is_asked_again_and_never_read(self, tmp_path: Path) -> None:
        # an export taken after a write (the link wave L5) names another source_url: the record of
        # the old one is stale - the next fetch asks the new URL, and nothing reads the old record
        H.export(
            tmp_path,
            reader=lambda sql: [row(A_ID, qid=None, source_url="https://heritage.example/old")],
        )
        calls: list[str] = []
        client = httpx.Client(transport=router(calls), follow_redirects=True)
        with fetcher(tmp_path, calls) as net:
            H.fetch_urls(net, client, tmp_path, H.read_sites(tmp_path), sleep=lambda s: None)
            H.export(
                tmp_path,
                reader=lambda sql: [
                    row(A_ID, qid=None, source_url="https://heritage.example/gone")
                ],
            )
            site = H.read_sites(tmp_path)[0]
            with pytest.raises(H.HarvestError, match="records 'https://heritage.example/old'"):
                H.load_url(tmp_path, site)
            assert H.status(tmp_path)["url_records"] == {"stale": 1}
            result = H.fetch_urls(net, client, tmp_path, [site], sleep=lambda s: None)
        assert result["asked"] == 1 and H.load_url(tmp_path, site)["status"] == 404

    def test_a_redirect_is_recorded_with_its_hops(self) -> None:
        client = httpx.Client(transport=router([]), follow_redirects=True)
        page = H.get_page(client, "https://heritage.example/moved")
        assert page["final_url"] == "https://heritage.example/other"
        assert page["hops"] == ["https://heritage.example/moved"]

    def test_one_host_is_asked_at_most_once_per_pace(self, tmp_path: Path) -> None:
        rows = [
            row(A_ID, qid=None, source_url="https://heritage.example/a"),
            row(B_ID, qid=None, source_url="https://heritage.example/b"),
        ]
        H.export(tmp_path, reader=lambda sql: rows)
        slept: list[float] = []
        clock = iter([0.0, 0.0, 0.2, 0.2, 0.2, 0.2])
        with fetcher(tmp_path, []) as net:
            H.fetch_urls(
                net, httpx.Client(transport=router([])), tmp_path, H.read_sites(tmp_path),
                sleep=slept.append, clock=lambda: next(clock), pace=1.0,
            )  # fmt: skip
        assert slept == [pytest.approx(0.8)]


class TestTheUrlKinds:
    @pytest.mark.parametrize(
        ("url", "kind"),
        [
            (None, H.URL_NONE),
            ("  ", H.URL_NONE),
            ("https://en.wikipedia.org/wiki/Stonehenge", H.URL_WIKIPEDIA),
            ("https://fr.m.wikipedia.org/wiki/Carnac", H.URL_WIKIPEDIA),
            ("https://whc.unesco.org/en/list/373/", H.URL_WEB),
            ("https://www.google.com.au/maps/place/x", H.URL_NOT_A_SOURCE),
            ("https://www-kulturportali-gov-tr.translate.goog/x", H.URL_NOT_A_SOURCE),
            ("http://127.0.0.1/x", H.URL_NOT_PUBLIC),
            ("https://a.example/x\nhttps://b.example/y", H.URL_MALFORMED),
            ("ftp://a.example/x", H.URL_MALFORMED),
        ],
    )
    def test_each_stored_url_is_asked_its_own_way(self, url: str | None, kind: str) -> None:
        assert H.url_kind(url) == kind

    def test_a_page_title_is_unescaped_and_collapsed(self) -> None:
        assert H.page_title(b"<TITLE lang=en>A &amp;\n B</title>", "utf-8") == "A & B"
        assert H.page_title(b"<html></html>", None) is None


class TestTheTransport:
    """The User-Agent without a contact address is refused by Wikimedia on httpx's own TLS
    handshake (ALPN) and by UNESCO on httpx's request (measured 2026-09-26); the transport sends
    through urllib3 and hands httpx the body as it came off the wire."""

    def test_the_request_leaves_through_requests_with_the_client_s_headers(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        seen: dict[str, Any] = {}

        class Raw:
            headers = {"Content-Type": "text/plain", "Content-Encoding": "identity"}

            def read(self, decode_content: bool) -> bytes:
                seen["decode_content"] = decode_content
                return b"hello"

        class Answer:
            status_code = 200
            raw = Raw()

            def close(self) -> None:
                seen["closed"] = True

        def request(self: Any, method: str, url: str, **kw: Any) -> Answer:
            seen.update(method=method, url=url, **kw)
            return Answer()

        monkeypatch.setattr(requests.Session, "request", request)
        with httpx.Client(
            transport=T.RequestsTransport(), headers={"User-Agent": H.USER_AGENT}
        ) as c:
            response = c.get("https://www.wikidata.org/w/api.php?a=1")
        assert response.text == "hello"
        assert seen["headers"]["user-agent"] == H.USER_AGENT
        assert "host" not in {k.lower() for k in seen["headers"]}
        assert seen["allow_redirects"] is False and seen["stream"] is True
        assert seen["decode_content"] is False and seen["closed"] is True

    @pytest.mark.parametrize(
        ("raised", "expected"),
        [
            (requests.Timeout("slow"), httpx.TimeoutException),
            (requests.ConnectionError("reset"), httpx.ConnectError),
            (requests.TooManyRedirects("loop"), httpx.TransportError),
        ],
    )
    def test_a_failure_is_the_httpx_error_of_its_kind(
        self, monkeypatch: pytest.MonkeyPatch, raised: Exception, expected: type
    ) -> None:
        def request(self: Any, method: str, url: str, **kw: Any) -> Any:
            raise raised

        monkeypatch.setattr(requests.Session, "request", request)
        with httpx.Client(transport=T.RequestsTransport()) as c, pytest.raises(expected):
            c.get("https://a.example/")
