"""Does S1b find a source for the unanchored sites, honour every refusal, and assign one lane each?

`phase4/route_stage.py` (WB-A3): the free routes (source_url, langlinks, geosearch), then MiniMax
behind the quota gate and the budget, then the lane - W, S, T, R or 0 - exactly once per site. And
that lane R reads a page with the one shared `pipeline.utils.text.extract_text_from_html`, which
`pipeline/lyra/handlers/content_fetch.py` re-exports.

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
from phase3 import search_evidence as SE  # noqa: E402
from phase3.model_stage import SEARCH_REPORT_NAME  # noqa: E402
from phase4 import licences as LIC  # noqa: E402
from phase4 import model4 as M  # noqa: E402
from phase4 import route_stage as RS  # noqa: E402
from phase4 import sources_stage as S1  # noqa: E402

from pipeline.lyra import minimax_shared as MX  # noqa: E402
from pipeline.lyra.handlers import content_fetch as CF  # noqa: E402
from tests.remediation.test_phase4_sources import (  # noqa: E402
    CUR,
    NOW,
    POINT,
    QID,
    SITE_ID,
    Web,
    article_answer,
    entity_answer,
    holds_of,
    invalid_answer,
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


def through_s1(
    tmp_path: Path, sites: list[M.PlanSite], web: Web, *, p625: tuple[float, float] | None = None
) -> Path:
    """S1 over `sites`; `p625` gives every stored item that point (the stored item has none)."""
    batch_dir = make_batch(tmp_path, sites)
    point = None if p625 is None else (p625[0], p625[1], 1e-4)
    for site in sites:
        if site.wikidata_qid is not None:
            phase3_file(tmp_path, site.site_id, entity_answer(site.wikidata_qid, p625=point))
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
    open_host(web, "https://grokipedia.com/page/Tarxien")
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


def assert_nothing_final(batch_dir: Path) -> None:
    """A stopped walk leaves no lane, no hold and no completion mark - only its two reports."""
    assert not (batch_dir / M.LANES_FILE).exists()
    assert not (batch_dir / RS.ROUTES_REPORT).exists()
    assert [h for h in holds_of(batch_dir) if h.detail.startswith("S1b: ")] == []
    assert (batch_dir / RS.ROUTES_FETCH_REPORT).exists()


def test_a_quota_gate_refusal_stops_the_run_and_a_resumed_run_searches(tmp_path: Path) -> None:
    """Review 2026-09-23: a quota stop wrote the lanes, the holds and routes.json, so the resumed
    run returned 0 and never searched the held sites - every floor hit lost up to 15 sites."""
    web = Web()
    batch_dir = through_s1(tmp_path, [unanchored()], web)
    empty_geosearch(web)
    refused = Probe({**GOOD_QUOTA, "weekly_remaining_percent": 20})

    assert run_routes(tmp_path, batch_dir, web, Searcher(), probe=refused) == R.STOP_RUN_EXIT

    assert_nothing_final(batch_dir)
    report = json.loads((batch_dir / SEARCH_REPORT_NAME).read_text(encoding="utf-8"))
    assert report["stopped"].startswith("the quota gate refused")

    first, second = queries()
    searcher = Searcher({first: [], second: []})
    assert run_routes(tmp_path, batch_dir, web, searcher, probe=Probe()) == 0

    assert searcher.asked == [first, second]
    (only,) = holds_of(batch_dir)
    assert only.reason is M.HoldReason.NO_SOURCE
    report = json.loads((batch_dir / SEARCH_REPORT_NAME).read_text(encoding="utf-8"))
    assert report["stopped"] is None
    assert len(report["quota"]) == 2  # the refused run's reading is carried forward


def test_a_failed_quota_probe_stops_like_a_refusal(tmp_path: Path) -> None:
    web = Web()
    batch_dir = through_s1(tmp_path, [unanchored()], web)
    empty_geosearch(web)
    probe = Probe({"ok": False, "error": "HTTP 500"})

    assert run_routes(tmp_path, batch_dir, web, Searcher(), probe=probe) == R.STOP_RUN_EXIT
    assert_nothing_final(batch_dir)


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
    assert_nothing_final(batch_dir)

    # The resumed run asks the query again (the failed one stored nothing) and counts every query
    # the batch sent, the stopped run's included.
    second = queries()[1]
    searcher = Searcher({first: [], second: []})
    assert run_routes(tmp_path, batch_dir, web, searcher) == 0
    assert searcher.asked == [first, second]
    report = json.loads((batch_dir / RS.ROUTES_REPORT).read_text(encoding="utf-8"))
    assert (report["queries"], report["search_requests"]) == (3, 3)


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
    report = json.loads((batch_dir / RS.ROUTES_REPORT).read_text(encoding="utf-8"))
    assert (report["queries"], report["search_requests"]) == (2, 2 * F.MAX_ATTEMPTS)


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
    first, second = queries()
    searcher = Searcher({first: [], second: []})

    assert run_routes(tmp_path, batch_dir, web, searcher) == R.STOP_RUN_EXIT

    assert_nothing_final(batch_dir)
    assert searcher.asked == []  # no search is bought for a site that cannot be judged


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
    assert ("pipeline.utils.text", "extract_text_from_html") in imported


# ====================================================================== review 2026-09-23


def test_a_wrong_subject_candidate_is_judged_on_its_own_item_not_the_sites(tmp_path: Path) -> None:
    """S1b judged every candidate of a QID site on the stored item: 'History' (a class) was no
    concept and, without coordinates, lay at the stored item's point - a parent page, lane S."""
    site = plan_site(enwiki_title=None, source_url="https://en.wikipedia.org/wiki/History")
    web = Web()
    batch_dir = through_s1(tmp_path, [site], web, p625=POINT)
    web.add(
        S1.article_url("en", "History"), article_answer(title="History", qid="Q309", coords=None)
    )
    web.add(
        S1.entity_url("Q309"),
        entity_answer("Q309", cur=CUR, p31=("Q1",), p279="Q1190554", labels={"en": "history"}),
    )
    web.add(S1.class_labels_url(["Q1"]), labels_answer({"Q1": "academic discipline"}))
    empty_geosearch(web)
    first, second = queries(site)

    assert run_routes(tmp_path, batch_dir, web, Searcher({first: [], second: []})) == 0

    (lane,) = lanes_of(batch_dir)
    assert lane.lane is M.Lane.ZERO
    assert "'History': wrong" in lane.detail
    assert S1.read_meta(store_of(batch_dir), SITE_ID, "W") is None
    d_meta = S1.read_meta(store_of(batch_dir), SITE_ID, "D")
    assert d_meta is not None and d_meta.route is M.Route.PHASE3_EVIDENCE  # never the page's item


def test_petras_invalid_title_reaches_its_source_url(tmp_path: Path) -> None:
    """Petra (no QID) stores `Petra`, a newline and a second URL as its title; S1 routes it and its
    source_url's first URL is its English article."""
    title = "Petra" + chr(10) + "https://www.khanacademy.org/a/petra"
    site = unanchored(
        wikidata_qid=None,
        name="Petra",
        country="Jordan",
        enwiki_title=title,
        source_url="https://en.wikipedia.org/wiki/Petra"
        + chr(10)
        + "https://www.khanacademy.org/a/petra",
    )
    web = Web().add(S1.article_url("en", title), invalid_answer(title))
    batch_dir = through_s1(tmp_path, [site], web)
    web.add(S1.article_url("en", "Petra"), article_answer(title="Petra", qid="Q5788"))
    web.add(S1.entity_url("Q5788"), entity_answer("Q5788", cur=CUR, labels={"en": "Petra"}))
    empty_geosearch(web)

    assert run_routes(tmp_path, batch_dir, web) == 0

    (lane,) = lanes_of(batch_dir)
    assert (lane.lane, lane.sources) == (M.Lane.W, ("W",))
    assert S1.read_meta(store_of(batch_dir), SITE_ID, "D") is not None


def test_an_invalid_candidate_title_is_an_answer_not_a_failure(tmp_path: Path) -> None:
    site = unanchored(source_url="https://en.wikipedia.org/wiki/Tarxien%0ATemples")
    web = Web()
    batch_dir = through_s1(tmp_path, [site], web)
    web.add(S1.article_url("en", "Tarxien" + chr(10) + "Temples"), invalid_answer("x"))
    empty_geosearch(web)
    first, second = queries(site)

    run_routes(tmp_path, batch_dir, web, Searcher({first: [], second: []}))

    (only,) = holds_of(batch_dir)
    assert only.reason is M.HoldReason.NO_SOURCE
    assert "an invalid title" in only.detail


def test_a_failed_wikipedia_route_holds_the_site_instead_of_a_lower_lane(tmp_path: Path) -> None:
    """Review 2026-09-23: the English article could not be asked (503 on every attempt), a web page
    passed every check, and the site went to lane R for good - its lane W lost to one outage."""
    site = unanchored(source_url="https://en.wikipedia.org/wiki/Tarxien_Temples")
    web = Web()
    batch_dir = through_s1(tmp_path, [site], web)
    web.add(S1.article_url("en", "Tarxien Temples"), b"busy", status=503)
    empty_geosearch(web)
    open_host(web)
    first, second = queries(site)

    assert run_routes(tmp_path, batch_dir, web, Searcher({first: [PAGE], second: [PAGE]})) == 0

    (lane,) = lanes_of(batch_dir)
    assert (lane.lane, lane.sources) == (M.Lane.ZERO, ())
    (only,) = holds_of(batch_dir)
    assert only.reason is M.HoldReason.FETCH_FAILED
    assert "HTTP 503" in only.detail
    assert S1.read_meta(store_of(batch_dir), SITE_ID, "R1") is None


def test_an_own_article_wins_lane_w_whatever_else_failed(tmp_path: Path) -> None:
    site = unanchored(source_url="https://en.wikipedia.org/wiki/Tarxien_Temples")
    web = Web()
    batch_dir = through_s1(tmp_path, [site], web)
    web.add(S1.article_url("en", "Tarxien Temples"), article_answer())
    web.add(RS.geosearch_url(*POINT), b"busy", status=503)

    assert run_routes(tmp_path, batch_dir, web) == 0

    assert lanes_of(batch_dir)[0].lane is M.Lane.W


def test_a_simple_english_hit_is_never_a_lane_r_page(tmp_path: Path) -> None:
    """Review 2026-09-23: simple.wikipedia.org is no article route, and was pinned as a lane-R
    'non-free' page under CC BY-SA 4.0 at the wiki cap."""
    simple = "https://simple.wikipedia.org/wiki/Tarxien_Temples"
    web = Web()
    batch_dir = through_s1(tmp_path, [unanchored()], web)
    empty_geosearch(web)
    open_host(web, simple)
    first, second = queries()

    run_routes(tmp_path, batch_dir, web, Searcher({first: [simple], second: []}))

    (lane,) = lanes_of(batch_dir)
    assert lane.lane is M.Lane.ZERO
    assert "never a lane-R page" in lane.detail
    assert web.asked("simple.wikipedia.org") == []


def test_a_page_that_redirects_into_wikipedia_is_never_a_lane_r_page(tmp_path: Path) -> None:
    web = Web()
    batch_dir = through_s1(tmp_path, [unanchored()], web)
    empty_geosearch(web)
    robots, tdmrep = RS.policy_urls(PAGE)
    web.add(robots, b"User-agent: *\nAllow: /\n").add(tdmrep, b"[]")
    wiki = "https://en.wikipedia.org/wiki/Tarxien_Temples"
    web.add(PAGE, redirect=wiki)
    open_host(web, wiki)
    first, second = queries()

    run_routes(tmp_path, batch_dir, web, Searcher({first: [PAGE], second: []}))

    (lane,) = lanes_of(batch_dir)
    assert lane.lane is M.Lane.ZERO
    assert f"redirected to {wiki}" in lane.detail


RESERVED = "https://heritage.example.org/private/tarxien"


@pytest.mark.parametrize(
    ("target", "target_policy"),
    [
        (RESERVED, None),  # same host: its tdmrep.json reserves /private/
        ("https://reserved.example.net/tarxien", b'[{"location": "/", "tdm-reservation": 1}]'),
    ],
    ids=["same-host-path", "other-host"],
)
def test_a_redirect_into_a_reserved_path_is_refused_and_deleted(
    tmp_path: Path, target: str, target_policy: bytes | None
) -> None:
    """Review 2026-09-23: the policy was checked again only when a redirect left the host; robots.txt
    and tdmrep.json reserve by path."""
    web = Web()
    batch_dir = through_s1(tmp_path, [unanchored()], web)
    empty_geosearch(web)
    robots, tdmrep = RS.policy_urls(PAGE)
    web.add(robots, b"User-agent: *\nAllow: /\n")
    web.add(tdmrep, b'[{"location": "/private/", "tdm-reservation": 1}]')
    web.add(PAGE, redirect=target)
    web.add(target, PAGE_HTML.encode("utf-8"))
    if target_policy is not None:
        other_robots, other_tdmrep = RS.policy_urls(target)
        web.add(other_robots, b"User-agent: *\nAllow: /\n").add(other_tdmrep, target_policy)
    first, second = queries()

    run_routes(tmp_path, batch_dir, web, Searcher({first: [PAGE], second: []}))

    (lane,) = lanes_of(batch_dir)
    assert lane.lane is M.Lane.ZERO
    assert "TDM refused: reserved" in lane.detail
    report = json.loads((batch_dir / RS.ROUTES_REPORT).read_text(encoding="utf-8"))
    (deleted,) = report["deleted_for_tdm"]
    assert not store_of(batch_dir).path_for(SITE_ID, deleted.split("/", 1)[1]).exists()


def test_a_page_that_is_not_utf8_counts_as_reserved_and_is_deleted(tmp_path: Path) -> None:
    """Review 2026-09-23: a latin-1 page with a reserving meta tag was never checked, never deleted."""
    latin = PAGE_HTML.replace("<head>", '<head><meta name="tdm-reservation" content="1">')
    web = Web()
    batch_dir = through_s1(tmp_path, [unanchored()], web)
    empty_geosearch(web)
    open_host(web)
    web.add(PAGE, latin.encode() + b" Tarxien Temples, Malta \xa6")  # a latin-1 byte
    first, second = queries()

    run_routes(tmp_path, batch_dir, web, Searcher({first: [PAGE], second: []}))

    (lane,) = lanes_of(batch_dir)
    assert lane.lane is M.Lane.ZERO and "not UTF-8" in lane.detail
    report = json.loads((batch_dir / RS.ROUTES_REPORT).read_text(encoding="utf-8"))
    (deleted,) = report["deleted_for_tdm"]
    assert not store_of(batch_dir).path_for(SITE_ID, deleted.split("/", 1)[1]).exists()


def _two_sites_one_down(tmp_path: Path, web: Web) -> tuple[Path, M.PlanSite, M.PlanSite]:
    """Site A searches first; site B's French source_url sits on a host that does not answer."""
    other = unanchored(
        site_id="4a5a324f-5555-4000-8000-000000000005",
        name="Hagar Qim",
        source_url="https://fr.wikipedia.org/wiki/Hagar_Qim",
    )
    batch_dir = through_s1(tmp_path, [unanchored(), other], web)
    empty_geosearch(web)
    web.down.add("fr.wikipedia.org")
    return batch_dir, unanchored(), other


def test_an_outage_later_in_the_batch_pins_nothing_for_the_sites_before_it(tmp_path: Path) -> None:
    """Review 2026-09-23: site A pinned R1 before site B hit the outage; the resumed run, where a page
    that had failed now answered, chose another R1 and died on EvidenceConflict."""
    second_page = "https://heritage.example.org/sites/tarxien-2"
    web = Web()
    batch_dir, site, _ = _two_sites_one_down(tmp_path, web)
    open_host(web)
    web.add(second_page, PAGE_HTML.encode("utf-8"))
    web.dead.add(PAGE)  # the first page does not answer in the first run
    first, second = queries(site)
    searcher = Searcher({first: [PAGE, second_page], second: []})

    assert run_routes(tmp_path, batch_dir, web, searcher) == R.STOP_RUN_EXIT

    assert_nothing_final(batch_dir)
    assert S1.read_meta(store_of(batch_dir), SITE_ID, "R1") is None

    web.dead.clear()
    web.down.clear()
    links = {"query": {"pages": [{"title": "Hagar Qim"}]}}
    web.add(RS.langlinks_url("fr", "Hagar Qim"), json.dumps(links).encode())
    web.add(S1.article_url("fr", "Hagar Qim"), article_answer(missing_title="Hagar Qim"))
    other_first, other_second = queries(unanchored(name="Hagar Qim"))
    searcher.answers.update({other_first: [], other_second: []})

    assert run_routes(tmp_path, batch_dir, web, searcher) == 0

    lane = lanes_of(batch_dir)[0]
    assert (lane.lane, lane.sources) == (M.Lane.R, ("R1", "R2"))
    r1 = S1.read_meta(store_of(batch_dir), SITE_ID, "R1")
    assert r1 is not None and r1.url == PAGE


def test_queries_bought_before_an_outage_are_counted(tmp_path: Path) -> None:
    """Review 2026-09-23: routes.json counted only the run that completed; the searches of the run an
    outage stopped were read back as existing and never counted."""
    web = Web()
    batch_dir = through_s1(tmp_path, [unanchored()], web)
    empty_geosearch(web)
    first, second = queries()
    searcher = Searcher({first: ["https://fr.wikipedia.org/wiki/Tarxien"], second: []})
    web.down.add("fr.wikipedia.org")

    assert run_routes(tmp_path, batch_dir, web, searcher) == R.STOP_RUN_EXIT
    assert searcher.asked == [first]

    web.down.clear()
    links = {"query": {"pages": [{"title": "Tarxien"}]}}
    web.add(RS.langlinks_url("fr", "Tarxien"), json.dumps(links).encode())
    web.add(S1.article_url("fr", "Tarxien"), article_answer(missing_title="Tarxien"))
    assert run_routes(tmp_path, batch_dir, web, searcher) == 0

    assert searcher.asked == [first, second]
    report = json.loads((batch_dir / RS.ROUTES_REPORT).read_text(encoding="utf-8"))
    assert (report["queries"], report["search_requests"]) == (2, 2)


def test_a_page_deleted_for_tdm_is_never_fetched_again_by_a_resumed_run(tmp_path: Path) -> None:
    reserved = PAGE_HTML.replace("<head>", '<head><meta name="tdm-reservation" content="1">')
    web = Web()
    batch_dir, site, _ = _two_sites_one_down(tmp_path, web)
    open_host(web, html=reserved)
    first, second = queries(site)
    searcher = Searcher({first: [PAGE], second: []})

    assert run_routes(tmp_path, batch_dir, web, searcher) == R.STOP_RUN_EXIT
    assert len(web.asked(PAGE)) == 1

    web.down.clear()
    links = {"query": {"pages": [{"title": "Hagar Qim"}]}}
    web.add(RS.langlinks_url("fr", "Hagar Qim"), json.dumps(links).encode())
    web.add(S1.article_url("fr", "Hagar Qim"), article_answer(missing_title="Hagar Qim"))
    other_first, other_second = queries(unanchored(name="Hagar Qim"))
    searcher.answers.update({other_first: [], other_second: []})

    assert run_routes(tmp_path, batch_dir, web, searcher) == 0

    assert len(web.asked(PAGE)) == 1
    report = json.loads((batch_dir / RS.ROUTES_REPORT).read_text(encoding="utf-8"))
    (deleted,) = report["deleted_for_tdm"]
    assert deleted.startswith(SITE_ID)
    assert "TDM refused: reserved (meta_tag)" in lanes_of(batch_dir)[0].detail


@pytest.mark.parametrize(
    ("page", "reason"),
    [
        ({"lastrevid": 101}, M.HoldReason.MOVED_DURING_FETCH),
        ({"timestamp": "2026-09-21T12:00:00Z"}, M.HoldReason.REVISION_TOO_FRESH),
    ],
    ids=["moved", "fresh"],
)
def test_an_article_s1b_found_is_held_by_the_rules_on_its_response(
    tmp_path: Path, page: dict[str, Any], reason: M.HoldReason
) -> None:
    site = unanchored(source_url="https://en.wikipedia.org/wiki/Tarxien_Temples")
    web = Web()
    batch_dir = through_s1(tmp_path, [site], web)
    web.add(S1.article_url("en", "Tarxien Temples"), article_answer(**page))
    empty_geosearch(web)

    assert run_routes(tmp_path, batch_dir, web) == 0

    (only,) = holds_of(batch_dir)
    assert (only.reason, only.detail.startswith("S1b: ")) == (reason, True)
    assert lanes_of(batch_dir)[0].lane is M.Lane.ZERO
    assert S1.read_meta(store_of(batch_dir), SITE_ID, "W") is None


def test_a_candidate_outside_the_article_namespace_is_never_kept(tmp_path: Path) -> None:
    site = unanchored(source_url="https://en.wikipedia.org/wiki/Tarxien_Temples")
    web = Web()
    batch_dir = through_s1(tmp_path, [site], web)
    web.add(S1.article_url("en", "Tarxien Temples"), article_answer(ns=4))
    empty_geosearch(web)
    first, second = queries(site)

    run_routes(tmp_path, batch_dir, web, Searcher({first: [], second: []}))

    (lane,) = lanes_of(batch_dir)
    assert lane.lane is M.Lane.ZERO and "namespace 4" in lane.detail


@pytest.mark.parametrize(
    ("robots", "why"),
    [
        (b"User-agent: *\nAllow: /\n#" + b"x" * F.MAX_PAGE_BYTES, "cut at the page cap"),
        (b"User-agent: *\nDisallow: /caf\xe9\n", "not UTF-8"),
    ],
    ids=["cut", "not-utf8"],
)
def test_a_policy_file_that_cannot_be_read_whole_refuses_the_page(
    tmp_path: Path, robots: bytes, why: str
) -> None:
    web = Web()
    batch_dir = through_s1(tmp_path, [unanchored()], web)
    empty_geosearch(web)
    robots_url, tdmrep_url = RS.policy_urls(PAGE)
    web.add(robots_url, robots).add(tdmrep_url, b"[]")
    web.add(PAGE, PAGE_HTML.encode("utf-8"))
    first, second = queries()

    run_routes(tmp_path, batch_dir, web, Searcher({first: [PAGE], second: []}))

    (lane,) = lanes_of(batch_dir)
    assert lane.lane is M.Lane.ZERO and why in lane.detail
    assert web.asked(PAGE) == []


def _pages(count: int) -> list[str]:
    return [f"https://heritage.example.org/sites/tarxien-{n}" for n in range(1, count + 1)]


def test_one_site_fetches_at_most_six_web_hits(tmp_path: Path) -> None:
    web = Web()
    batch_dir = through_s1(tmp_path, [unanchored()], web)
    empty_geosearch(web)
    robots, tdmrep = RS.policy_urls(PAGE)
    web.add(robots, b"User-agent: *\nAllow: /\n").add(tdmrep, b"[]")
    for url in _pages(8):
        web.add(url, b"<p>Hagar Qim is a temple in Malta.</p>")  # every one fails web identity
    first, second = queries()

    run_routes(tmp_path, batch_dir, web, Searcher({first: _pages(8), second: []}))

    assert sum(1 for url in _pages(8) if web.asked(url)) == RS.MAX_WEB_FETCHES_PER_SITE == 6


def test_one_site_pins_at_most_three_lane_r_pages(tmp_path: Path) -> None:
    web = Web()
    batch_dir = through_s1(tmp_path, [unanchored()], web)
    empty_geosearch(web)
    robots, tdmrep = RS.policy_urls(PAGE)
    web.add(robots, b"User-agent: *\nAllow: /\n").add(tdmrep, b"[]")
    for url in _pages(5):
        web.add(url, PAGE_HTML.encode("utf-8"))
    first, second = queries()

    run_routes(tmp_path, batch_dir, web, Searcher({first: _pages(5), second: []}))

    (lane,) = lanes_of(batch_dir)
    assert (lane.lane, lane.sources) == (M.Lane.R, ("R1", "R2", "R3"))
    assert RS.MAX_R_PAGES_PER_SITE == 3


def test_a_stored_search_for_another_query_stops_the_stage(tmp_path: Path) -> None:
    web = Web()
    batch_dir = through_s1(tmp_path, [unanchored()], web)
    empty_geosearch(web)
    record = SE.SearchRecord(query="a query another template built", hits=(), linkless=0)
    store_of(batch_dir).write(
        site_id=SITE_ID, feature=RS.route_slot(1).feature, body=record.to_bytes()
    )
    searcher = Searcher()

    with pytest.raises(R.InputError, match="a changed query needs a new run directory"):
        run_routes(tmp_path, batch_dir, web, searcher)
    assert searcher.asked == []


def test_a_sources_report_without_a_site_of_the_batch_stops_the_stage(tmp_path: Path) -> None:
    web = Web()
    batch_dir = through_s1(tmp_path, [unanchored()], web)
    report_path = batch_dir / S1.SOURCES_REPORT
    report = json.loads(report_path.read_text(encoding="utf-8"))
    report["sites"] = []
    report_path.write_text(json.dumps(report), encoding="utf-8")

    with pytest.raises(R.InputError, match="has no outcome for"):
        run_routes(tmp_path, batch_dir, web)


def test_a_stopped_walk_asks_nothing_for_the_sites_after_it(tmp_path: Path) -> None:
    """Once the run must stop, a later site's routes are not asked: nothing they found could count."""
    later = unanchored(
        site_id="4a5a324f-6666-4000-8000-000000000006", name="Hal Saflieni", lat=35.87, lon=14.51
    )
    web = Web()
    batch_dir = through_s1(tmp_path, [unanchored(), later], web)
    empty_geosearch(web)
    empty_geosearch(web, later.lat, later.lon)
    refused = Probe({**GOOD_QUOTA, "weekly_remaining_percent": 20})

    assert run_routes(tmp_path, batch_dir, web, Searcher(), probe=refused) == R.STOP_RUN_EXIT

    assert web.asked(RS.geosearch_url(later.lat, later.lon)) == []
