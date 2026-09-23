"""Does S1b find a source for the unanchored sites, honour every refusal, and assign one lane each?

`phase4/route_stage.py` (WB-A3): the free routes (source_url, langlinks, geosearch), then MiniMax
behind the quota gate and the budget, then the lane - W, S, T, R or 0 - exactly once per site. And
the rename WB-A3 owns in `pipeline/lyra/handlers/content_fetch.py`.

Nothing opens a socket and nothing calls MiniMax: the network is the scripted `Web` of
`test_phase4_sources` behind the real `HttpFetcher`, the searcher is scripted and refuses a query
nobody scripted, and the quota probe is a dict. Every stage runs for real: S1 first, then S1b over
what S1 left on disk. The mutation cases are `PHASE4_SOURCES_MUTATIONS` in
`scripts/remediation/phase3/mutation_sweep.py`.
"""

from __future__ import annotations

import ast
import json
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[2]
PHASE4_PARENT = REPO / "scripts" / "remediation"
if str(PHASE4_PARENT) not in sys.path:
    sys.path.insert(0, str(PHASE4_PARENT))

from phase3 import fetch_stage as F  # noqa: E402
from phase3 import run as R  # noqa: E402
from phase3.model_stage import SEARCH_REPORT_NAME  # noqa: E402
from phase4 import licences as LIC  # noqa: E402
from phase4 import model4 as M  # noqa: E402
from phase4 import route_stage as RS  # noqa: E402
from phase4 import sources_stage as S1  # noqa: E402

from pipeline.lyra import minimax_shared as MX  # noqa: E402
from pipeline.lyra.handlers import content_fetch as CF  # noqa: E402
from tests.remediation.test_phase4_sources import (  # noqa: E402
    NOW,
    POINT,
    QID,
    SITE_ID,
    Web,
    article_answer,
    entity_answer,
    holds_of,
    labels_answer,
    make_batch,
    phase3_file,
    plan_site,
    store_of,
)

ENDPOINT = "https://api.minimax.io/v1/coding_plan/search"
GOOD_QUOTA = {
    "ok": True,
    "five_hour_remaining_percent": 80,
    "weekly_remaining_percent": 80,
    "weekly_remains_tokens": 10_000_000,
    "five_hour_remains_tokens": 1_000_000,
}
PAGE = "https://heritage.example.org/sites/tarxien"
PAGE_HTML = (
    "<html><head><title>Tarxien</title><script>var x = 1;</script></head><body>"
    "<h1>The Tarxien Temples</h1><p>The Tarxien Temples in Malta are a megalithic complex "
    "built between 3600 and 2500 BC.</p></body></html>"
)
FAR = (POINT[0] + 1.0, POINT[1])


class Searcher:
    """MiniMax, scripted: a query gets its hit URLs or its error. Any other query is a test bug."""

    endpoint = ENDPOINT

    def __init__(self, answers: Mapping[str, list[str] | Exception] | None = None) -> None:
        self.answers = dict(answers or {})
        self.asked: list[str] = []

    def search(self, query: str) -> MX.SearchResponse:
        self.asked.append(query)
        if query not in self.answers:
            raise AssertionError(f"an unscripted search: {query!r}")
        answer = self.answers[query]
        if isinstance(answer, Exception):
            raise answer
        items = tuple(
            MX.WebSearchResult(title=f"hit {n}", url=url, snippet="never evidence", date="")
            for n, url in enumerate(answer, start=1)
        )
        return MX.SearchResponse(query=query, items=items, http_status=200, body_bytes=100)


def queries(site: M.PlanSite | None = None) -> tuple[str, str]:
    first, second = RS.route_queries(site or plan_site())
    return first, second


class Probe:
    def __init__(self, reading: Mapping[str, Any] = GOOD_QUOTA) -> None:
        self.reading = dict(reading)
        self.calls = 0

    def __call__(self) -> Mapping[str, Any]:
        self.calls += 1
        return self.reading


def unanchored(**over: Any) -> M.PlanSite:
    """A site S1 cannot anchor: no enwiki_title; its source_url is not Wikipedia by default."""
    base: dict[str, Any] = {
        "enwiki_title": None,
        "source_url": "https://www.example.com/tarxien",
    }
    base.update(over)
    return plan_site(**base)


def through_s1(tmp_path: Path, sites: list[M.PlanSite], web: Web) -> Path:
    batch_dir = make_batch(tmp_path, sites)
    for site in sites:
        if site.wikidata_qid is not None:
            phase3_file(tmp_path, site.site_id, entity_answer(site.wikidata_qid))
    web.add(S1.class_labels_url(["Q839954"]), labels_answer({"Q839954": "archaeological site"}))
    code = S1.sources_batch(
        batch_dir,
        ledger=tmp_path / "LEDGER.jsonl",
        fetcher=web.fetcher(),
        now=NOW,
        phase3_run=tmp_path / "phase3",
        sleep=lambda _: None,
    )
    assert code == 0
    return batch_dir


def run_routes(
    tmp_path: Path,
    batch_dir: Path,
    web: Web,
    searcher: Searcher | None = None,
    *,
    budget: int = 10,
    probe: Probe | None = None,
) -> int:
    return RS.routes_batch(
        batch_dir,
        ledger=tmp_path / "LEDGER.jsonl",
        fetcher=web.fetcher(),
        searcher=searcher or Searcher(),
        max_searches=budget,
        now=NOW,
        probe=probe or Probe(),
        wait=lambda: None,
        sleep=lambda _: None,
    )


def lanes_of(batch_dir: Path) -> list[M.LaneAssignment]:
    return M.load_jsonl(batch_dir / M.LANES_FILE, M.LaneAssignment)


def empty_geosearch(web: Web, lat: float = POINT[0], lon: float = POINT[1]) -> Web:
    return web.add(RS.geosearch_url(lat, lon), json.dumps({"query": {"geosearch": []}}).encode())


def geosearch(web: Web, titles: list[str]) -> Web:
    rows = [{"pageid": n, "ns": 0, "title": t, "dist": 10.0 * n} for n, t in enumerate(titles)]
    return web.add(RS.geosearch_url(*POINT), json.dumps({"query": {"geosearch": rows}}).encode())


def open_host(web: Web, url: str = PAGE, html: str = PAGE_HTML) -> Web:
    robots, tdmrep = RS.policy_urls(url)
    web.add(robots, b"User-agent: *\nAllow: /\n")
    web.add(tdmrep, b"[]")
    return web.add(url, html.encode("utf-8"))


# ======================================================================= lanes from S1's outcome


def test_an_article_s1_pinned_own_is_lane_w_and_nothing_is_asked(tmp_path: Path) -> None:
    web = Web().add(S1.article_url("en", "Tarxien Temples"), article_answer())
    batch_dir = through_s1(tmp_path, [plan_site()], web)
    web.calls.clear()
    searcher = Searcher()

    assert run_routes(tmp_path, batch_dir, web, searcher) == 0

    (lane,) = lanes_of(batch_dir)
    assert (lane.lane, lane.sources) == (M.Lane.W, ("W",))
    assert web.calls == [] and searcher.asked == []


def test_an_article_s1_pinned_shared_is_lane_s(tmp_path: Path) -> None:
    web = Web().add(S1.article_url("en", "Tarxien Temples"), article_answer())
    site = plan_site(flags=frozenset({M.SiteFlag.SHARED_QID}))
    batch_dir = through_s1(tmp_path, [site], web)

    run_routes(tmp_path, batch_dir, web)

    (lane,) = lanes_of(batch_dir)
    assert (lane.lane, lane.sources) == (M.Lane.S, ("W",))


def test_a_site_s1_held_is_lane_0_and_keeps_only_s1s_hold(tmp_path: Path) -> None:
    site = plan_site(flags=frozenset({M.SiteFlag.SCOPE_PENDING}))
    batch_dir = through_s1(tmp_path, [site], Web())

    assert run_routes(tmp_path, batch_dir, Web()) == 0

    (lane,) = lanes_of(batch_dir)
    assert lane.lane is M.Lane.ZERO and lane.detail.startswith("held in S1")
    assert [h.reason for h in holds_of(batch_dir)] == [M.HoldReason.SCOPE_PENDING]


def test_the_routes_need_s1s_report(tmp_path: Path) -> None:
    batch_dir = make_batch(tmp_path, [plan_site()])
    with pytest.raises(R.InputError, match="run the sources stage first"):
        run_routes(tmp_path, batch_dir, Web())


# ================================================================================ free routes


def test_an_english_source_url_is_a_candidate_through_s1s_gate(tmp_path: Path) -> None:
    site = unanchored(source_url="https://en.wikipedia.org/wiki/Tarxien_Temples")
    web = Web()
    batch_dir = through_s1(tmp_path, [site], web)
    web.add(S1.article_url("en", "Tarxien Temples"), article_answer())
    empty_geosearch(web)
    searcher = Searcher()

    assert run_routes(tmp_path, batch_dir, web, searcher) == 0

    (lane,) = lanes_of(batch_dir)
    assert (lane.lane, lane.sources) == (M.Lane.W, ("W",))
    meta = S1.read_meta(store_of(batch_dir), SITE_ID, "W")
    assert meta is not None and meta.route is M.Route.SOURCE_URL
    assert meta.permalink == "https://en.wikipedia.org/w/index.php?title=Tarxien_Temples&oldid=100"
    assert searcher.asked == []
    assert len(web.asked("list=geosearch")) == 1  # every free route is resolved and recorded


def test_a_qid_less_site_is_judged_on_its_pages_item_and_pins_it_as_src_d(tmp_path: Path) -> None:
    site = unanchored(wikidata_qid=None, source_url="https://en.wikipedia.org/wiki/Tarxien_Temples")
    web = Web()
    batch_dir = through_s1(tmp_path, [site], web)
    web.add(S1.article_url("en", "Tarxien Temples"), article_answer())
    web.add(S1.entity_url(QID), entity_answer(QID, cur="2026-09-22T12:00:05Z", p31=("Q9",)))
    web.add(S1.class_labels_url(["Q9"]), labels_answer({"Q9": "megalithic temple"}))
    empty_geosearch(web)

    assert run_routes(tmp_path, batch_dir, web) == 0

    (lane,) = lanes_of(batch_dir)
    assert (lane.lane, lane.sources) == (M.Lane.W, ("W",))
    store = store_of(batch_dir)
    w_meta, d_meta = S1.read_meta(store, SITE_ID, "W"), S1.read_meta(store, SITE_ID, "D")
    assert w_meta is not None and w_meta.subject_gate is not None
    assert (w_meta.subject_gate.verdict, w_meta.subject_gate.qid_match) == (
        M.SubjectVerdict.OWN,
        False,
    )
    assert d_meta is not None and d_meta.route is M.Route.WIKIDATA_ENTITY
    assert d_meta.retrieved_at == "2026-09-22T12:00:05Z"


def test_a_qid_less_site_whose_page_item_cannot_be_read_gets_no_article(tmp_path: Path) -> None:
    site = unanchored(wikidata_qid=None, source_url="https://en.wikipedia.org/wiki/Tarxien_Temples")
    web = Web()
    batch_dir = through_s1(tmp_path, [site], web)
    web.add(S1.article_url("en", "Tarxien Temples"), article_answer())
    web.add(S1.entity_url(QID), b"", status=404)
    empty_geosearch(web)
    first, second = queries(site)

    run_routes(tmp_path, batch_dir, web, Searcher({first: [], second: []}))

    (lane,) = lanes_of(batch_dir)
    assert lane.lane is M.Lane.ZERO
    assert S1.read_meta(store_of(batch_dir), SITE_ID, "W") is None


def test_every_url_of_a_multi_line_source_url_is_a_route(tmp_path: Path) -> None:
    both = "https://www.megalithic.co.uk/article.php?sid=16211\nhttps://en.wikipedia.org/wiki/Tarxien_Temples"
    site = unanchored(source_url=both)
    web = Web()
    batch_dir = through_s1(tmp_path, [site], web)
    web.add(S1.article_url("en", "Tarxien Temples"), article_answer())
    empty_geosearch(web)

    run_routes(tmp_path, batch_dir, web)

    assert RS.source_urls(site) == both.split("\n")
    assert lanes_of(batch_dir)[0].lane is M.Lane.W
    assert RS.source_urls(plan_site(source_url=None)) == []


def test_another_languages_source_url_goes_through_its_english_langlink(tmp_path: Path) -> None:
    site = unanchored(source_url="https://fr.wikipedia.org/wiki/Temples_de_Tarxien")
    web = Web()
    batch_dir = through_s1(tmp_path, [site], web)
    links = {
        "query": {
            "pages": [
                {
                    "title": "Temples de Tarxien",
                    "langlinks": [{"lang": "en", "title": "Tarxien Temples"}],
                }
            ]
        }
    }
    web.add(RS.langlinks_url("fr", "Temples de Tarxien"), json.dumps(links).encode())
    web.add(S1.article_url("en", "Tarxien Temples"), article_answer())
    empty_geosearch(web)

    run_routes(tmp_path, batch_dir, web)

    (lane,) = lanes_of(batch_dir)
    assert lane.lane is M.Lane.W
    meta = S1.read_meta(store_of(batch_dir), SITE_ID, "W")
    assert meta is not None and meta.route is M.Route.LANGLINKS
    fr_article = "fr.wikipedia.org/w/api.php?action=query&format=json&formatversion=2&redirects=1"
    assert web.asked(fr_article + "&prop=extracts") == []


def test_an_own_article_only_in_another_language_is_lane_t(tmp_path: Path) -> None:
    site = unanchored(source_url="https://fr.wikipedia.org/wiki/Temples_de_Tarxien")
    web = Web()
    batch_dir = through_s1(tmp_path, [site], web)
    no_links = {"query": {"pages": [{"title": "Temples de Tarxien"}]}}
    web.add(RS.langlinks_url("fr", "Temples de Tarxien"), json.dumps(no_links).encode())
    web.add(S1.article_url("fr", "Temples de Tarxien"), article_answer(title="Temples de Tarxien"))
    empty_geosearch(web)
    first, second = queries(site)
    searcher = Searcher({first: [], second: []})

    run_routes(tmp_path, batch_dir, web, searcher)

    (lane,) = lanes_of(batch_dir)
    assert (lane.lane, lane.sources) == (M.Lane.T, ("T.fr",))
    meta = S1.read_meta(store_of(batch_dir), SITE_ID, "T.fr")
    assert meta is not None
    assert (
        meta.permalink == "https://fr.wikipedia.org/w/index.php?title=Temples_de_Tarxien&oldid=100"
    )
    assert meta.licence is M.Licence.CC_BY_SA_4
    assert meta.route is M.Route.SOURCE_URL
    assert searcher.asked == [first, second]  # "only in another language" needs the search


def test_geosearch_keeps_only_articles_that_carry_the_stored_name(tmp_path: Path) -> None:
    web = Web()
    batch_dir = through_s1(tmp_path, [unanchored()], web)
    geosearch(web, ["Paola, Malta", "Tarxien Temples", "Tarxien"])
    web.add(S1.article_url("en", "Tarxien Temples"), article_answer())

    run_routes(tmp_path, batch_dir, web)

    (lane,) = lanes_of(batch_dir)
    assert lane.lane is M.Lane.W
    meta = S1.read_meta(store_of(batch_dir), SITE_ID, "W")
    assert meta is not None and meta.route is M.Route.GEOSEARCH
    assert web.asked("titles=Paola") == [] and web.asked("titles=Tarxien&") == []


def test_the_article_s1_rejected_is_not_asked_again(tmp_path: Path) -> None:
    web = Web().add(S1.article_url("en", "Tarxien Temples"), article_answer(coords=FAR))
    batch_dir = through_s1(tmp_path, [plan_site(source_url=None)], web)
    geosearch(web, ["Tarxien Temples"])
    first, second = queries()
    web.calls.clear()

    run_routes(tmp_path, batch_dir, web, Searcher({first: [], second: []}))

    assert web.asked("titles=Tarxien%20Temples") == []
    (lane,) = lanes_of(batch_dir)
    assert lane.lane is M.Lane.ZERO


# ==================================================================================== MiniMax


def test_the_queries_are_name_site_type_and_country() -> None:
    site = plan_site(name='Arkheologicheskiy Muzey "Tanais"', site_type="City", country="Russia")
    assert RS.route_queries(site) == (
        '"Arkheologicheskiy Muzey Tanais" City Russia',
        "Arkheologicheskiy Muzey Tanais City Russia",
    )
    assert len(RS.route_queries(plan_site())) == RS.MAX_QUERIES_PER_SITE == 2


def test_a_wikipedia_hit_goes_back_through_s1_and_wins_lane_w(tmp_path: Path) -> None:
    web = Web()
    batch_dir = through_s1(tmp_path, [unanchored()], web)
    empty_geosearch(web)
    web.add(S1.article_url("en", "Tarxien Temples"), article_answer())
    first, _ = queries()
    searcher = Searcher({first: ["https://en.m.wikipedia.org/wiki/Tarxien_Temples"]})

    assert run_routes(tmp_path, batch_dir, web, searcher) == 0

    (lane,) = lanes_of(batch_dir)
    assert lane.lane is M.Lane.W
    meta = S1.read_meta(store_of(batch_dir), SITE_ID, "W")
    assert meta is not None and meta.route is M.Route.MINIMAX
    assert searcher.asked == [first]  # the second query is not bought once a source is own


def test_a_web_page_that_passes_every_check_is_pinned_as_lane_r(tmp_path: Path) -> None:
    web = Web()
    batch_dir = through_s1(tmp_path, [unanchored()], web)
    empty_geosearch(web)
    open_host(web)
    first, second = queries()

    assert run_routes(tmp_path, batch_dir, web, Searcher({first: [PAGE], second: [PAGE]})) == 0

    (lane,) = lanes_of(batch_dir)
    assert (lane.lane, lane.sources) == (M.Lane.R, ("R1",))
    store = store_of(batch_dir)
    meta = S1.read_meta(store, SITE_ID, "R1")
    text = store.path_for(SITE_ID, "src.R1.txt").read_text(encoding="utf-8")
    assert meta is not None
    assert meta.licence is M.Licence.RESTRICTED
    assert meta.route is M.Route.MINIMAX
    assert meta.tdm == M.Tdm(checked=True, reserved=False, signal=None)
    assert (meta.final_url, meta.truncated) == (PAGE, False)
    assert text == CF.extract_text_from_html(PAGE_HTML)
    assert "var x" not in text
    assert store.path_for(SITE_ID, "src.R1").read_bytes() == PAGE_HTML.encode("utf-8")


def test_a_search_snippet_is_never_evidence(tmp_path: Path) -> None:
    web = Web()
    batch_dir = through_s1(tmp_path, [unanchored()], web)
    empty_geosearch(web)
    open_host(web)
    first, second = queries()
    run_routes(tmp_path, batch_dir, web, Searcher({first: [PAGE], second: []}))

    text = store_of(batch_dir).path_for(SITE_ID, "src.R1.txt").read_text(encoding="utf-8")
    assert "never evidence" not in text


@pytest.mark.parametrize(
    "url", ["https://grokipedia.com/page/Tarxien", "https://www.wikiwand.com/en/Tarxien_Temples"]
)
def test_a_denied_host_is_never_asked(tmp_path: Path, url: str) -> None:
    web = Web()
    batch_dir = through_s1(tmp_path, [unanchored()], web)
    empty_geosearch(web)
    first, second = queries()

    run_routes(tmp_path, batch_dir, web, Searcher({first: [url], second: [url]}))

    assert web.asked(LIC.host_of(url)) == []
    (only,) = holds_of(batch_dir)
    assert only.reason is M.HoldReason.NO_SOURCE


@pytest.mark.parametrize(
    ("robots", "robots_status", "tdmrep", "tdmrep_status", "allowed"),
    [
        (b"User-agent: *\nAllow: /\n", 200, b"[]", 200, True),
        (b"", 404, b"", 404, True),
        (b"User-agent: *\nDisallow: /sites/\n", 200, b"[]", 200, False),
        (b"", 503, b"[]", 200, False),
        (b"User-agent: *\nAllow: /\n", 200, b"<html>not json</html>", 200, False),
        (
            b"User-agent: *\nAllow: /\n",
            200,
            b'[{"location": "/", "tdm-reservation": 1}]',
            200,
            False,
        ),
        (b"", 429, b"[]", 200, False),
    ],
    ids=[
        "open",
        "absent",
        "robots-disallow",
        "robots-5xx",
        "tdmrep-not-json",
        "tdmrep-reserves",
        "robots-rate-limited",
    ],
)
def test_the_tdm_check_runs_before_the_page_and_a_failed_check_refuses_it(
    tmp_path: Path,
    robots: bytes,
    robots_status: int,
    tdmrep: bytes,
    tdmrep_status: int,
    allowed: bool,
) -> None:
    web = Web()
    batch_dir = through_s1(tmp_path, [unanchored()], web)
    empty_geosearch(web)
    robots_url, tdmrep_url = RS.policy_urls(PAGE)
    web.add(robots_url, robots, status=robots_status)
    web.add(tdmrep_url, tdmrep, status=tdmrep_status)
    web.add(PAGE, PAGE_HTML.encode("utf-8"))
    first, second = queries()

    run_routes(tmp_path, batch_dir, web, Searcher({first: [PAGE], second: [PAGE]}))

    (lane,) = lanes_of(batch_dir)
    assert (lane.lane is M.Lane.R) is allowed
    assert bool(web.asked(PAGE)) is allowed  # a refused page is never fetched


def test_a_page_whose_html_reserves_tdm_is_deleted_after_the_check(tmp_path: Path) -> None:
    reserved = PAGE_HTML.replace("<head>", '<head><meta name="tdm-reservation" content="1">')
    web = Web()
    batch_dir = through_s1(tmp_path, [unanchored()], web)
    empty_geosearch(web)
    open_host(web, html=reserved)
    first, second = queries()

    run_routes(tmp_path, batch_dir, web, Searcher({first: [PAGE], second: [PAGE]}))

    (lane,) = lanes_of(batch_dir)
    assert lane.lane is M.Lane.ZERO
    report = json.loads((batch_dir / RS.ROUTES_REPORT).read_text(encoding="utf-8"))
    (deleted,) = set(report["deleted_for_tdm"])
    feature = deleted.split("/", 1)[1]
    assert not store_of(batch_dir).path_for(SITE_ID, feature).exists()


def test_a_page_that_redirects_to_a_denied_host_is_refused(tmp_path: Path) -> None:
    web = Web()
    batch_dir = through_s1(tmp_path, [unanchored()], web)
    empty_geosearch(web)
    robots, tdmrep = RS.policy_urls(PAGE)
    web.add(robots, b"User-agent: *\nAllow: /\n").add(tdmrep, b"[]")
    web.add(PAGE, redirect="https://grokipedia.com/page/Tarxien")
    web.add("https://grokipedia.com/page/Tarxien", PAGE_HTML.encode("utf-8"))
    first, second = queries()

    run_routes(tmp_path, batch_dir, web, Searcher({first: [PAGE], second: [PAGE]}))

    (lane,) = lanes_of(batch_dir)
    assert lane.lane is M.Lane.ZERO
    assert "denied" in lane.detail


def test_a_page_that_never_names_the_site_fails_web_identity(tmp_path: Path) -> None:
    web = Web()
    batch_dir = through_s1(tmp_path, [unanchored()], web)
    empty_geosearch(web)
    open_host(web, html="<p>Hagar Qim is a temple in Malta.</p>")
    first, second = queries()

    run_routes(tmp_path, batch_dir, web, Searcher({first: [PAGE], second: [PAGE]}))

    assert lanes_of(batch_dir)[0].lane is M.Lane.ZERO


def test_web_identity_wants_the_name_and_the_country_or_a_nearby_point() -> None:
    site = plan_site()
    assert RS.web_identity(site, "The Tarxien Temples, Malta.") is None
    assert RS.web_identity(site, "The Tarxien Temples (35.8690, 14.5120).") is None
    assert RS.web_identity(site, "The Tarxien Temples (36.9690, 14.5120).") is not None
    assert RS.web_identity(site, "The Tarxien Temples somewhere.") is not None
    assert RS.web_identity(site, "Temples of Malta.") is not None
    assert RS.web_identity(site, "The TarxienTemples, Malta.") is not None  # whole words only


def test_a_page_that_copies_the_sites_wikipedia_text_is_a_mirror(tmp_path: Path) -> None:
    long_extract = " ".join(f"word{n}" for n in range(60)) + " Tarxien Temples Malta."
    web = Web().add(
        S1.article_url("en", "Tarxien Temples"), article_answer(coords=FAR, extract=long_extract)
    )
    batch_dir = through_s1(tmp_path, [plan_site(source_url=None)], web)
    empty_geosearch(web)
    copy = "<p>Tarxien Temples, Malta. " + " ".join(f"word{n}" for n in range(10, 40)) + "</p>"
    open_host(web, html=copy)
    first, second = queries()

    run_routes(tmp_path, batch_dir, web, Searcher({first: [PAGE], second: [PAGE]}))

    (lane,) = lanes_of(batch_dir)
    assert lane.lane is M.Lane.ZERO
    assert "mirror" in lane.detail


def test_at_most_two_queries_per_site(tmp_path: Path) -> None:
    web = Web()
    batch_dir = through_s1(tmp_path, [unanchored()], web)
    empty_geosearch(web)
    first, second = queries()
    searcher = Searcher({first: [], second: []})

    run_routes(tmp_path, batch_dir, web, searcher)

    assert searcher.asked == [first, second]
    (only,) = holds_of(batch_dir)
    assert only.reason is M.HoldReason.NO_SOURCE
    assert only.detail.startswith("S1b: ")


def test_a_quota_gate_refusal_holds_the_site_and_stops_the_run(tmp_path: Path) -> None:
    web = Web()
    batch_dir = through_s1(tmp_path, [unanchored()], web)
    empty_geosearch(web)
    searcher = Searcher()
    probe = Probe({**GOOD_QUOTA, "weekly_remaining_percent": 20})

    assert run_routes(tmp_path, batch_dir, web, searcher, probe=probe) == R.STOP_RUN_EXIT

    assert searcher.asked == []
    (only,) = holds_of(batch_dir)
    assert only.reason is M.HoldReason.SEARCH_STOPPED
    assert lanes_of(batch_dir)[0].lane is M.Lane.ZERO
    report = json.loads((batch_dir / SEARCH_REPORT_NAME).read_text(encoding="utf-8"))
    assert report["stopped"].startswith("the quota gate refused")


def test_a_failed_quota_probe_stops_like_a_refusal(tmp_path: Path) -> None:
    web = Web()
    batch_dir = through_s1(tmp_path, [unanchored()], web)
    empty_geosearch(web)
    probe = Probe({"ok": False, "error": "HTTP 500"})

    assert run_routes(tmp_path, batch_dir, web, Searcher(), probe=probe) == R.STOP_RUN_EXIT
    assert holds_of(batch_dir)[0].reason is M.HoldReason.SEARCH_STOPPED


def test_a_spent_budget_holds_the_site_and_the_batch_still_completes(tmp_path: Path) -> None:
    web = Web()
    batch_dir = through_s1(tmp_path, [unanchored()], web)
    empty_geosearch(web)
    searcher = Searcher()

    probe = Probe()

    assert run_routes(tmp_path, batch_dir, web, searcher, budget=0, probe=probe) == 0

    assert searcher.asked == [] and probe.calls == 0
    (only,) = holds_of(batch_dir)
    assert only.reason is M.HoldReason.SEARCH_STOPPED
    assert "budget" in only.detail


def test_a_stop_class_search_error_stops_the_run(tmp_path: Path) -> None:
    web = Web()
    batch_dir = through_s1(tmp_path, [unanchored()], web)
    empty_geosearch(web)
    first, _ = queries()
    searcher = Searcher({first: MX.CodingPlanAuthError("401", http_status=401, body_bytes=10)})

    assert run_routes(tmp_path, batch_dir, web, searcher) == R.STOP_RUN_EXIT

    assert searcher.asked == [first]
    assert holds_of(batch_dir)[0].reason is M.HoldReason.SEARCH_STOPPED


def test_searches_that_could_not_be_made_hold_fetch_failed_not_no_source(tmp_path: Path) -> None:
    web = Web()
    batch_dir = through_s1(tmp_path, [unanchored()], web)
    empty_geosearch(web)
    first, second = queries()
    reset = MX.CodingPlanTransportError("connection reset")
    searcher = Searcher({first: reset, second: reset})

    assert run_routes(tmp_path, batch_dir, web, searcher) == 0

    assert searcher.asked == [first] * F.MAX_ATTEMPTS + [second] * F.MAX_ATTEMPTS
    (only,) = holds_of(batch_dir)
    assert only.reason is M.HoldReason.FETCH_FAILED


def test_the_budget_counts_queries_across_the_batch(tmp_path: Path) -> None:
    other = unanchored(site_id="4a5a324f-3333-4000-8000-000000000003", name="Hal Saflieni")
    web = Web()
    batch_dir = through_s1(tmp_path, [unanchored(), other], web)
    empty_geosearch(web)
    first, second = queries()
    searcher = Searcher({first: [], second: []})

    run_routes(tmp_path, batch_dir, web, searcher, budget=2)

    assert searcher.asked == [first, second]
    reasons = {h.site_id: h.reason for h in holds_of(batch_dir)}
    assert reasons == {
        SITE_ID: M.HoldReason.NO_SOURCE,
        other.site_id: M.HoldReason.SEARCH_STOPPED,
    }


# ===================================================================================== outputs


def test_every_site_gets_exactly_one_lane_line_in_batch_order(tmp_path: Path) -> None:
    held = plan_site(
        site_id="4a5a324f-4444-4000-8000-000000000004", flags=frozenset({M.SiteFlag.SCOPE_PENDING})
    )
    web = Web()
    batch_dir = through_s1(tmp_path, [unanchored(), held], web)
    empty_geosearch(web)
    first, second = queries()

    run_routes(tmp_path, batch_dir, web, Searcher({first: [], second: []}))

    assert [lane.site_id for lane in lanes_of(batch_dir)] == [SITE_ID, held.site_id]
    report = json.loads((batch_dir / RS.ROUTES_REPORT).read_text(encoding="utf-8"))
    assert report["queries"] == 2
    assert (batch_dir / RS.ROUTES_FETCH_REPORT).exists()


def test_a_finished_batch_is_not_routed_again(tmp_path: Path) -> None:
    web = Web()
    batch_dir = through_s1(tmp_path, [unanchored()], web)
    empty_geosearch(web)
    first, second = queries()
    searcher = Searcher({first: [], second: []})
    run_routes(tmp_path, batch_dir, web, searcher)
    web.calls.clear()

    assert run_routes(tmp_path, batch_dir, web, searcher) == 0
    assert web.calls == [] and searcher.asked == [first, second]


def test_a_wiki_host_outage_in_s1b_stops_and_leaves_nothing_final(tmp_path: Path) -> None:
    web = Web()
    batch_dir = through_s1(tmp_path, [unanchored()], web)
    web.down.add("en.wikipedia.org")

    assert run_routes(tmp_path, batch_dir, web) == R.STOP_RUN_EXIT

    assert not (batch_dir / M.LANES_FILE).exists()
    assert not (batch_dir / RS.ROUTES_REPORT).exists()


def test_a_negative_or_boolean_budget_is_refused(tmp_path: Path) -> None:
    batch_dir = make_batch(tmp_path, [plan_site()])
    for budget in (-1, True):
        with pytest.raises(R.InputError, match="not a count"):
            run_routes(tmp_path, batch_dir, Web(), budget=budget)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://en.wikipedia.org/wiki/Tarxien_Temples", ("en", "Tarxien Temples")),
        ("https://en.m.wikipedia.org/wiki/Tarxien_Temples", ("en", "Tarxien Temples")),
        ("https://fr.wikipedia.org/wiki/Temples_de_Tarxien", ("fr", "Temples de Tarxien")),
        ("https://de.wikipedia.org/wiki/%C4%A6al_Saflieni", ("de", "Ħal Saflieni")),
        ("https://simple.wikipedia.org/wiki/Stonehenge", None),
        ("https://en.wikipedia.org/w/index.php?title=X", None),
        ("https://wikipedia.org/wiki/X", None),
        ("https://en.wikipedia.org.example.com/wiki/X", None),
        ("not a url", None),
    ],
)
def test_a_wikipedia_article_url_names_its_edition_and_title(
    url: str, expected: tuple[str, str] | None
) -> None:
    assert RS.wikipedia_title(url) == expected


def test_the_live_search_seams_are_the_search_lanes_own(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    probes: list[bool] = []
    closed: list[bool] = []

    class Live:
        endpoint = ENDPOINT

        def close(self) -> None:
            closed.append(True)

    monkeypatch.setattr(RS.SS.MiniMaxSearcher, "from_settings", classmethod(lambda cls: Live()))
    monkeypatch.setattr(
        MX, "probe_minimax_quota", lambda force=False: probes.append(force) or GOOD_QUOTA
    )

    with RS.open_search(pacing_dir=tmp_path / "pacing") as (searcher, probe, wait):
        assert isinstance(searcher, Live)
        assert probe() == GOOD_QUOTA
        wait()
        wait()
    assert probes == [True]  # never a cached reading
    assert closed == [True]
    stamp = tmp_path / "pacing" / "api.minimax.io.stamp"
    assert stamp.exists()


# ================================================================================ content_fetch


def test_the_page_text_function_is_public_and_its_old_name_is_gone_everywhere() -> None:
    assert CF.extract_text_from_html("<p>a</p><script>b</script>") == "a"
    assert not hasattr(CF, "_extract_text_from_html")
    for root in ("pipeline", "scripts", "api", "tests"):
        for path in (REPO / root).rglob("*.py"):
            # This file names the old spelling to look for it, and the mutation sweep carries it as
            # the mutant that proves this test goes red.
            if path.resolve() == Path(__file__).resolve() or path.name == "mutation_sweep.py":
                continue
            assert "_extract_text_from_html" not in path.read_text(encoding="utf-8"), path


def test_the_lane_r_text_comes_through_the_shared_function() -> None:
    tree = ast.parse((PHASE4_PARENT / "phase4" / "route_stage.py").read_text(encoding="utf-8"))
    imported = {
        (node.module, alias.name)
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        for alias in node.names
    }
    assert ("pipeline.lyra.handlers.content_fetch", "extract_text_from_html") in imported
