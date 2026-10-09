"""D17 (2026-10-08): the candidate search's routes, the population it reads, and the MiniMax pool.

DB-less and offline: Commons and Wikipedia are an `httpx.MockTransport` for the client tests and a
dictionary-backed stub for the routes; the Wikidata items are dictionaries behind the entity store's
`get`.
"""

from __future__ import annotations

import hashlib
import json
import sys
import threading
from pathlib import Path
from typing import Any

import httpx
import pytest

REPO = Path(__file__).resolve().parents[2]
for _p in (REPO, REPO / "scripts" / "remediation"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from candidate_search import judge as CJ  # noqa: E402
from candidate_search import pool as PL  # noqa: E402
from candidate_search import population as PP  # noqa: E402
from candidate_search import search as CS  # noqa: E402
from import_hero import plan as IH  # noqa: E402
from served_image import commons as CM  # noqa: E402
from served_image import state as ST  # noqa: E402

FLOOR = (IH.OWNER_FLOOR_WIDTH, IH.OWNER_FLOOR_HEIGHT)
SITE = "0d9bd81d-d41c-4381-8e2e-7626928fedc1"


# ============================================================================ the Commons client
def _client(handler: Any) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


class TestTheGeosearch:
    def test_files_within_the_radius_nearest_first_in_title_form(self, tmp_path: Path) -> None:
        seen: list[dict[str, str]] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(dict(httpx.QueryParams(request.content.decode())))
            hits = [
                {"title": "File:Near_gate.jpg", "dist": 12.5},
                {"title": "File:Far wall.jpg", "dist": 280.0},
            ]
            return httpx.Response(200, json={"query": {"geosearch": hits}})

        commons = CM.Commons(tmp_path, _client(handler), pace=0)
        got = commons.geosearch(40.5, 24.5, 300, 20)
        assert got == [("Near gate.jpg", 12.5), ("Far wall.jpg", 280.0)]
        (params,) = seen
        assert params["list"] == "geosearch" and params["gsradius"] == "300"
        assert params["gsnamespace"] == "6" and params["gscoord"] == "40.5|24.5"
        assert params["gslimit"] == "20"
        assert commons.geosearch(40.5, 24.5, 300, 20) == got and len(seen) == 1  # cached

    def test_an_empty_answer_is_a_valid_cached_answer(self, tmp_path: Path) -> None:
        calls: list[int] = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(1)
            return httpx.Response(200, json={"query": {"geosearch": []}})

        commons = CM.Commons(tmp_path, _client(handler), pace=0)
        assert commons.geosearch(1.0, 2.0, 300, 20) == []
        assert commons.geosearch(1.0, 2.0, 300, 20) == [] and len(calls) == 1

    def test_a_refused_query_raises(self, tmp_path: Path) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"error": {"code": "toobig"}})

        with pytest.raises(CM.CommonsError, match="refused"):
            CM.Commons(tmp_path, _client(handler), pace=0).geosearch(1.0, 2.0, 300, 20)


class TestTheWikipediaImages:
    def _page(self, **over: Any) -> dict[str, Any]:
        page = {
            "title": "Troy",
            "pageimage": "Troy_walls.jpg",
            "images": [
                {"ns": 6, "title": "File:Troy walls.jpg"},
                {"ns": 6, "title": "File:Map.svg"},
            ],
        }
        return page | over

    def test_the_lead_and_the_files_in_page_order(self, tmp_path: Path) -> None:
        asked: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            asked.append(str(request.url))
            return httpx.Response(200, json={"query": {"pages": [self._page()]}})

        commons = CM.Commons(tmp_path, _client(handler), pace=0)
        got = commons.wikipedia_images("Troy")
        assert got == {
            "missing": False,
            "lead": "Troy walls.jpg",
            "files": ["Troy walls.jpg", "Map.svg"],
        }
        assert asked[0].startswith("https://en.wikipedia.org/w/api.php")
        commons.wikipedia_images("Troy")
        assert len(asked) == 1

    def test_an_article_that_does_not_exist_is_missing_not_empty(self, tmp_path: Path) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200, json={"query": {"pages": [{"title": "Nowhere", "missing": True}]}}
            )

        got = CM.Commons(tmp_path, _client(handler), pace=0).wikipedia_images("Nowhere")
        assert got == {"missing": True, "lead": None, "files": []}

    def test_an_article_without_a_lead_image_has_none(self, tmp_path: Path) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            page = {"title": "Troy"}
            return httpx.Response(200, json={"query": {"pages": [page]}})

        got = CM.Commons(tmp_path, _client(handler), pace=0).wikipedia_images("Troy")
        assert got == {"missing": False, "lead": None, "files": []}

    def test_a_failed_request_raises(self, tmp_path: Path) -> None:
        commons = CM.Commons(tmp_path, _client(lambda r: httpx.Response(429)), pace=0)
        with pytest.raises(CM.CommonsError, match="HTTP 429"):
            commons.wikipedia_images("Troy")

    def test_an_answer_of_two_pages_is_refused(self, tmp_path: Path) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"query": {"pages": [self._page(), self._page()]}})

        with pytest.raises(CM.CommonsError, match="2 pages"):
            CM.Commons(tmp_path, _client(handler), pace=0).wikipedia_images("Troy")


class TestTwoWorkersOneClient:
    def test_a_save_keeps_the_entries_another_worker_wrote(self, tmp_path: Path) -> None:
        commons = CM.Commons(tmp_path, _client(lambda r: httpx.Response(200, json={})), pace=0)
        commons._save("search", {"a": 1})
        commons._save("search", {"b": 2})  # the second writer never loaded "a"
        assert commons._load("search") == {"a": 1, "b": 2}

    def test_two_threads_saving_at_once_tear_nothing(self, tmp_path: Path) -> None:
        commons = CM.Commons(tmp_path, _client(lambda r: httpx.Response(200, json={})), pace=0)

        def write(prefix: str) -> None:
            for i in range(25):
                commons._save("search", {f"{prefix}{i}": i})

        threads = [threading.Thread(target=write, args=(p,)) for p in "ab"]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert len(commons._load("search")) == 50

    def test_requests_of_one_host_stay_a_pace_apart_even_from_two_threads(
        self, tmp_path: Path
    ) -> None:
        now = [0.0]
        waits: list[float] = []

        def sleep(seconds: float) -> None:
            waits.append(seconds)
            now[0] += seconds

        commons = CM.Commons(
            tmp_path, _client(lambda r: httpx.Response(200, json={})), pace=1.0, sleep=sleep,
            clock=lambda: now[0],
        )  # fmt: skip
        threads = [
            threading.Thread(target=commons._wait, args=("https://x.org/a",)) for _ in range(3)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert waits == [1.0, 1.0]


# ========================================================================== the routes
class Store:
    def __init__(self, entities: dict[str, dict[str, Any]]) -> None:
        self.entities = entities

    def get(self, qid: str) -> tuple[dict[str, Any] | None, str | None]:
        entity = self.entities.get(qid)
        return (entity, "harvest") if entity else (None, None)

    def missing(self, qids: Any) -> list[str]:
        return sorted({q for q in qids if self.get(q)[0] is None})


def _claim(value: str) -> dict[str, Any]:
    return {"mainsnak": {"datavalue": {"value": value}}, "rank": "normal"}


def item(
    *, p18: list[str] = (), p373: list[str] = (), commonswiki: str | None = None
) -> dict[str, Any]:  # type: ignore[assignment]
    sitelinks = {} if commonswiki is None else {"commonswiki": {"title": commonswiki}}
    return {
        "id": "Q9",
        "claims": {"P18": [_claim(v) for v in p18], "P373": [_claim(v) for v in p373]},
        "sitelinks": sitelinks,
    }


class FakeCommons:
    """Every question the routes ask, answered from dictionaries; `asked` records them in order."""

    def __init__(self) -> None:
        self.hits: dict[str, list[str]] = {}
        self.categories: dict[str, list[str]] = {}
        self.articles: dict[str, dict[str, Any]] = {}
        self.geo: list[tuple[str, float]] = []
        self.boxes: dict[str, tuple[int, int]] = {}
        self.asked: list[str] = []

    def search(self, term: str, limit: int) -> list[str]:
        self.asked.append(term)
        return self.hits.get(term, [])[:limit]

    def members(self, category: str, limit: int) -> list[str]:
        self.asked.append(f"category:{category}")
        return self.categories.get(category, [])[:limit]

    def wikipedia_images(self, title: str) -> dict[str, Any]:
        self.asked.append(f"wikipedia:{title}")
        return self.articles.get(title, {"missing": True, "lead": None, "files": []})

    def geosearch(self, lat: float, lon: float, radius: int, limit: int) -> list[tuple[str, float]]:
        self.asked.append(f"geosearch:{lat}|{lon}|{radius}|{limit}")
        return self.geo

    def imageinfo(self, files: Any) -> dict[str, dict[str, Any]]:
        return {
            f: {
                "status": CM.OK,
                "title": f,
                "url": f"https://upload.wikimedia.org/wikipedia/commons/a/ab/{f.replace(' ', '_')}",
                "render_url": f"https://thumb.wikimedia.org/1280px-{f.replace(' ', '_')}",
                "mime": "image/jpeg",
            }
            for f in files
        }

    def sizes(self, files: Any) -> dict[str, tuple[int, int]]:
        return {f: self.boxes.get(f, (3000, 2000)) for f in files}


def site(**over: Any) -> dict[str, Any]:
    base = {"site_id": SITE, "name": "Monte Lazzu", "country": "France", "lat": 42.07, "lon": 8.73}
    return base | over


def routes_of(result: CS.SiteResult) -> dict[str, str]:
    return {c["file"]: c["route"] for c in result.candidates}


class TestTheRoutes:
    def test_a_name_only_site_asks_exactly_what_it_always_asked(self) -> None:
        commons = FakeCommons()
        CS.site_candidates(commons, site(), floor=FLOOR)
        assert commons.asked == [
            "Monte Lazzu filetype:bitmap",
            'intitle:"Monte Lazzu" filetype:bitmap',
            "category:Monte Lazzu",
        ]

    def test_the_items_image_and_category_are_the_first_routes(self) -> None:
        commons = FakeCommons()
        commons.categories["Monte Lazzu (site)"] = ["Cat1.jpg", "Cat2.jpg"]
        store = Store({"Q9": item(p18=["Wd.jpg"], p373=["Monte Lazzu (site)"])})
        result = CS.site_candidates(commons, site(qid="Q9"), floor=FLOOR, entities=store)
        assert routes_of(result) == {"Wd.jpg": "p18", "Cat1.jpg": "p373", "Cat2.jpg": "p373"}
        assert "(P18)" in result.candidates[0]["why"]

    def test_the_commons_category_the_item_links_is_read(self) -> None:
        commons = FakeCommons()
        commons.categories["Category:Lazzu"] = ["Linked.jpg"]
        store = Store({"Q9": item(commonswiki="Category:Lazzu")})
        result = CS.site_candidates(commons, site(qid="Q9"), floor=FLOOR, entities=store)
        assert routes_of(result) == {"Linked.jpg": "commonswiki"}

    def test_a_commons_gallery_page_is_not_a_category_and_is_noted(self) -> None:
        store = Store({"Q9": item(commonswiki="Monte Lazzu")})
        result = CS.site_candidates(FakeCommons(), site(qid="Q9"), floor=FLOOR, entities=store)
        assert any("gallery page" in n for n in result.notes)

    def test_structured_data_depicts_is_asked_for_the_item(self) -> None:
        commons = FakeCommons()
        commons.hits["haswbstatement:P180=Q9 filetype:bitmap"] = ["Sdc.jpg"]
        result = CS.site_candidates(
            commons, site(qid="Q9"), floor=FLOOR, entities=Store({"Q9": item()})
        )
        assert routes_of(result) == {"Sdc.jpg": "sdc_p180"}
        assert "P180" in result.candidates[0]["why"]

    def test_the_articles_lead_image_and_page_images_without_vector_art(self) -> None:
        commons = FakeCommons()
        commons.articles["Monte Lazzu"] = {
            "missing": False,
            "lead": "Lead.jpg",
            "files": ["Lead.jpg", "Map.svg", "Page.jpg", "Song.ogg"],
        }
        result = CS.site_candidates(commons, site(enwiki_title="Monte Lazzu"), floor=FLOOR)
        assert routes_of(result) == {"Lead.jpg": "enwiki_lead", "Page.jpg": "enwiki_page"}

    def test_a_lead_image_that_is_vector_art_is_not_a_candidate(self) -> None:
        commons = FakeCommons()
        commons.articles["T"] = {"missing": False, "lead": "Logo.svg", "files": []}
        result = CS.site_candidates(commons, site(enwiki_title="T"), floor=FLOOR)
        assert result.reason == CS.NO_CANDIDATE

    def test_an_article_that_does_not_exist_is_noted_by_name(self) -> None:
        result = CS.site_candidates(FakeCommons(), site(enwiki_title="Gone"), floor=FLOOR)
        assert any("does not exist" in n for n in result.notes)

    def test_two_items_give_no_item_route_and_say_so(self) -> None:
        commons = FakeCommons()
        result = CS.site_candidates(
            commons, site(qid=None, qid_conflict=["Q1", "Q2"]), floor=FLOOR, entities=Store({})
        )
        assert any("two Wikidata items (Q1, Q2)" in n for n in result.notes)
        assert not any(a.startswith("haswbstatement") for a in commons.asked)

    def test_two_titles_give_no_article_route_and_say_so(self) -> None:
        commons = FakeCommons()
        result = CS.site_candidates(
            commons, site(enwiki_title=None, enwiki_conflict=["A", "B"]), floor=FLOOR
        )
        assert any("two Wikipedia titles" in n for n in result.notes)
        assert not any(a.startswith("wikipedia:") for a in commons.asked)

    def test_an_item_the_store_does_not_hold_is_an_error_not_an_empty_claim(self) -> None:
        with pytest.raises(CS.SearchError, match="neither the harvest nor its delta"):
            CS.site_candidates(FakeCommons(), site(qid="Q404"), floor=FLOOR, entities=Store({}))

    def test_a_site_with_an_item_and_no_store_is_an_error(self) -> None:
        with pytest.raises(CS.SearchError, match="no entity store"):
            CS.site_candidates(FakeCommons(), site(qid="Q9"), floor=FLOOR)

    def test_the_researched_category_and_local_names_are_searched(self) -> None:
        commons = FakeCommons()
        commons.categories["Lazzu archaeological site"] = ["Cat.jpg"]
        commons.hits['intitle:"Lazu" filetype:bitmap'] = ["Local.jpg"]
        result = CS.site_candidates(
            commons,
            site(commons_category="Lazzu archaeological site", local_names=["Lazu", "monte lazzu"]),
            floor=FLOOR,
        )
        assert routes_of(result) == {"Cat.jpg": "researched_category", "Local.jpg": "local_name"}
        # the local name equal to the name (folded) is searched once, as the name
        assert commons.asked.count("Monte Lazzu filetype:bitmap") == 1

    def test_the_geotag_route_runs_only_for_a_sourced_point_and_carries_the_distance(self) -> None:
        commons = FakeCommons()
        commons.geo = [("Near.jpg", 41.26), ("Far.jpg", 290.0)]
        result = CS.site_candidates(commons, site(coord_sourced=True), floor=FLOOR)
        assert routes_of(result) == {"Near.jpg": "geosearch", "Far.jpg": "geosearch"}
        assert result.candidates[0]["distance_m"] == 41.3
        assert "geosearch:42.07|8.73|300|20" in commons.asked

    def test_an_unsourced_point_is_never_searched_around_and_the_note_says_why(self) -> None:
        commons = FakeCommons()
        result = CS.site_candidates(commons, site(coord_sourced=False), floor=FLOOR)
        assert not any(a.startswith("geosearch") for a in commons.asked)
        assert "geotag route skipped: the point is not sourced" in result.notes

    def test_a_file_named_by_two_routes_keeps_the_first(self) -> None:
        commons = FakeCommons()
        commons.articles["T"] = {"missing": False, "lead": "Both.jpg", "files": []}
        commons.hits["Monte Lazzu filetype:bitmap"] = ["Both.jpg"]
        result = CS.site_candidates(commons, site(enwiki_title="T"), floor=FLOOR)
        assert routes_of(result) == {"Both.jpg": "enwiki_lead"}

    def test_the_gallery_files_and_the_judged_files_are_never_offered(self) -> None:
        commons = FakeCommons()
        commons.hits["Monte Lazzu filetype:bitmap"] = ["Held.jpg", "Judged.jpg", "New.jpg"]
        result = CS.site_candidates(
            commons,
            site(held_files=["Held.jpg"], judged_not_depicts=["Judged.jpg"]),
            floor=FLOOR,
            exclude=[],
        )
        assert routes_of(result) == {"New.jpg": "name"}

    def test_the_floor_is_the_runs(self) -> None:
        commons = FakeCommons()
        commons.hits["Monte Lazzu filetype:bitmap"] = ["Small.jpg"]
        commons.boxes["Small.jpg"] = (799, 600)
        assert CS.site_candidates(commons, site(), floor=FLOOR).reason == CS.ALL_TOO_SMALL
        assert CS.site_candidates(commons, site(), floor=(799, 600)).reason == ""

    def test_a_site_keeps_sixty_candidates_and_names_the_rest(self) -> None:
        commons = FakeCommons()
        files = [f"F{i:03d}.jpg" for i in range(75)]
        commons.categories["Monte Lazzu"] = files
        # a category is read at HITS_PER_QUERY: lift it for the test
        original = CS.HITS_PER_QUERY
        CS.HITS_PER_QUERY = 100
        try:
            result = CS.site_candidates(commons, site(), floor=FLOOR)
        finally:
            CS.HITS_PER_QUERY = original
        assert len(result.candidates) == CS.MAX_CANDIDATES == 60
        assert result.capped == files[60:]

    def test_a_site_without_a_name_is_refused_by_name(self) -> None:
        assert CS.site_candidates(FakeCommons(), site(name=" "), floor=FLOOR).reason == CS.NO_NAME


class TestTheRun:
    def _sites(self) -> list[dict[str, Any]]:
        return [site(site_id=f"s{i}", name=f"Site {i}") for i in range(4)]

    def _commons(self) -> FakeCommons:
        commons = FakeCommons()
        commons.hits["Site 1 filetype:bitmap"] = ["One.jpg"]
        commons.hits["Site 2 filetype:bitmap"] = ["Two.jpg"]
        return commons

    def test_two_workers_answer_what_one_worker_answers(self, tmp_path: Path) -> None:
        one = CS.run(tmp_path / "one", self._sites(), self._commons(), floor=FLOOR, workers=1)
        two = CS.run(tmp_path / "two", self._sites(), self._commons(), floor=FLOOR, workers=2)
        assert one == two
        assert (tmp_path / "one" / CS.CANDIDATES).read_text() == (
            tmp_path / "two" / CS.CANDIDATES
        ).read_text()

    def test_the_summary_counts_candidates_by_route_and_notes(self, tmp_path: Path) -> None:
        sites = [site(site_id="a", name="Site 1", coord_sourced=False)]
        summary = CS.run(tmp_path, sites, self._commons(), floor=FLOOR)
        assert summary["candidates_by_route"] == {"name": 1}
        assert summary["notes"] == {"geotag route skipped: the point is not sourced": 1}
        row = json.loads((tmp_path / CS.CANDIDATES).read_text(encoding="utf-8"))
        assert row["notes"] and row["capped"] == [] and row["candidates"][0]["route"] == "name"

    def test_the_refusals_keep_their_notes(self, tmp_path: Path) -> None:
        CS.run(
            tmp_path,
            [site(site_id="z", name="Nothing", coord_sourced=False)],
            FakeCommons(),
            floor=FLOOR,
        )
        (refusal,) = [
            json.loads(x) for x in (tmp_path / CS.REFUSALS).read_text(encoding="utf-8").splitlines()
        ]
        assert refusal["reason"] == CS.NO_CANDIDATE and refusal["notes"]

    @pytest.mark.parametrize("workers", [0, 3])
    def test_at_most_two_sites_at_once(self, tmp_path: Path, workers: int) -> None:
        with pytest.raises(CS.SearchError, match="workers must be 1..2"):
            CS.run(tmp_path, self._sites(), self._commons(), floor=FLOOR, workers=workers)

    def test_the_routes_are_a_closed_list(self) -> None:
        assert CS.ROUTES == (
            "p18", "p373", "commonswiki", "sdc_p180", "enwiki_lead", "enwiki_page",
            "researched_category", "name", "local_name", "geosearch",
        )  # fmt: skip
        assert (CS.GEOSEARCH_RADIUS_M, CS.GEOSEARCH_LIMIT, CS.MAX_WORKERS) == (300, 20, 2)


# ======================================================================== the population
def read_line(**over: Any) -> dict[str, Any]:
    base = {
        "site_id": SITE, "name": "Monte Lazzu", "country": "France", "site_type": "Settlement",
        "lat": 42.07, "lon": 8.73, "description": "A site.", "qids": ["Q9"], "enwiki_titles": ["Monte Lazzu"],
        "coord_kind": None, "coord_marker_current": False, "rows": [],
    }  # fmt: skip
    return base | over


class TestThePopulation:
    def test_the_sql_defines_serving_no_picture_and_is_read_only(self) -> None:
        sql = PP.population_sql()
        assert (
            "NOT EXISTS (SELECT 1 FROM wiki_images w WHERE w.site_id = u.id AND NOT w.is_excluded)"
            in sql
        )
        assert "coalesce(u.thumbnail_url, '') = ''" in sql
        assert "scope_status IS DISTINCT FROM 'retired'" in sql
        assert "site_external_ids" in sql and "wikidata_qid" in sql and "enwiki_title" in sql
        assert "_coord_provenance" in sql
        assert not any(word in sql.upper() for word in ("INSERT ", "UPDATE ", "DELETE ", "DROP "))

    def test_the_sql_can_be_limited_to_named_sites(self) -> None:
        assert f"AND u.id IN ('{SITE}'::uuid)" in PP.population_sql([SITE])
        assert "u.id IN" not in PP.population_sql()

    def test_the_single_item_and_title_come_from_the_external_ids(self) -> None:
        record = PP.site_record(read_line())
        assert (record["qid"], record["qid_conflict"], record["enwiki_title"]) == (
            "Q9",
            None,
            "Monte Lazzu",
        )

    def test_two_items_are_a_conflict_and_no_item(self) -> None:
        record = PP.site_record(read_line(qids=["Q2", "Q1"], enwiki_titles=["A", "B"]))
        assert record["qid"] is None and record["qid_conflict"] == ["Q1", "Q2"]
        assert record["enwiki_title"] is None and record["enwiki_conflict"] == ["A", "B"]

    def test_no_identity_is_none_and_no_conflict(self) -> None:
        record = PP.site_record(read_line(qids=[], enwiki_titles=[]))
        assert (record["qid"], record["qid_conflict"], record["enwiki_title"]) == (None, None, None)

    @pytest.mark.parametrize(
        ("kind", "current", "sourced"),
        [
            ("quote", True, True),
            ("two_source", True, True),
            ("authoritative", True, True),
            ("import_kept", True, True),
            ("unsourced", True, False),
            ("quote", False, False),  # the marker no longer hashes the point
            (None, False, False),  # no marker (the lane has not written it yet)
            ("bogus", True, False),
        ],
    )
    def test_a_point_is_sourced_only_by_a_current_marker_of_a_sourced_kind(
        self, kind: str | None, current: bool, sourced: bool
    ) -> None:
        record = PP.site_record(read_line(coord_kind=kind, coord_marker_current=current))
        assert record["coord_sourced"] is sourced

    def test_the_files_of_every_row_are_held_the_excluded_ones_too(self) -> None:
        rows = [
            {"filename": "a.webp", "original_url": "https://upload.wikimedia.org/wikipedia/commons/a/ab/Held_one.jpg", "commons_page_url": None, "is_excluded": False},
            {"filename": "b.webp", "original_url": "https://upload.wikimedia.org/wikipedia/commons/a/ab/Old_excluded.jpg", "commons_page_url": None, "is_excluded": True},
            {"filename": "c.webp", "original_url": "https://upload.wikimedia.org/wikipedia/commons/a/ab/Held_one.jpg", "commons_page_url": None, "is_excluded": False},
        ]  # fmt: skip
        assert PP.held_files(rows) == ["Held one.jpg", "Old excluded.jpg"]

    def test_the_population_is_sorted_and_a_site_twice_is_refused(self) -> None:
        built = PP.build([read_line(site_id="b"), read_line(site_id="a")])
        assert [s["site_id"] for s in built] == ["a", "b"]
        with pytest.raises(PP.PopulationError, match="twice"):
            PP.build([read_line(), read_line()])

    def test_the_population_is_written_once_and_read_back(self, tmp_path: Path) -> None:
        sites = PP.build([read_line()])
        PP.write_population(tmp_path / PP.POPULATION_FILE, sites)
        assert PP.load_population(tmp_path / PP.POPULATION_FILE) == sites
        with pytest.raises(ST.StateError, match="written once"):
            PP.write_population(tmp_path / PP.POPULATION_FILE, sites)
        with pytest.raises(PP.PopulationError, match="empty"):
            PP.write_population(tmp_path / "x.jsonl", [])
        with pytest.raises(PP.PopulationError, match="does not exist"):
            PP.load_population(tmp_path / "none.jsonl")

    def test_the_counts_report_what_the_population_is_made_of(self) -> None:
        sites = PP.build(
            [
                read_line(site_id="a"),
                read_line(site_id="b", qids=[], enwiki_titles=[]),
                read_line(site_id="c", qids=["Q1", "Q2"]),
            ]
        )
        got = PP.counts(sites)
        assert (got["sites"], got["with_qid"], got["qid_conflict"], got["no_identity"]) == (
            3,
            1,
            1,
            1,
        )

    def test_the_sourced_kinds_are_the_marker_lane_s_minus_unsourced(self) -> None:
        assert PP.SOURCED_KINDS == {"quote", "two_source", "authoritative", "import_kept"}


# ============================================================================== the pool
def _pool_run(tmp_path: Path) -> Path:
    old = tmp_path / "candidates-2026-10-06"
    (old / "pictures").mkdir(parents=True)
    candidates = [
        {
            "site_id": "a", "name": "Site a", "country": "Italy",
            "candidates": [
                {"file": "Here.jpg", "picture_url": "https://thumb.wikimedia.org/h.jpg", "width": 3000, "height": 2000},
                {"file": "Gone.jpg", "picture_url": "https://thumb.wikimedia.org/g.jpg", "width": 3000, "height": 2000},
            ],
        },
        {"site_id": "b", "name": "Site b", "country": "Italy", "candidates": [
            {"file": "B.jpg", "picture_url": "https://thumb.wikimedia.org/b.jpg", "width": 900, "height": 600}]},
    ]  # fmt: skip
    (old / "CANDIDATES.jsonl").write_text(
        "".join(json.dumps(c) + "\n" for c in candidates), encoding="utf-8"
    )
    name = hashlib.sha256(b"https://thumb.wikimedia.org/h.jpg").hexdigest()[:32]
    (old / "pictures" / name).write_bytes(b"jpeg")
    verdicts = [
        {"site_id": "a", "file": "Here.jpg", "verdict": "depicts", "note": "the tomb", "answered_by": "mcode-judge-1", "model": "MiniMax-M3.1-Flash-Preview"},
        {"site_id": "a", "file": "Gone.jpg", "verdict": "other_site", "note": "n", "answered_by": "mcode-judge-1", "model": "m"},
    ]  # fmt: skip
    (old / CJ.VERDICTS).write_text(
        "".join(json.dumps(v) + "\n" for v in verdicts), encoding="utf-8"
    )
    (old / CJ.TARGETS).write_text(
        json.dumps({"site_id": "a", "commons_file": "Here.jpg", "width": 3000, "height": 2000})
        + "\n",
        encoding="utf-8",
    )
    return old


class TestThePool:
    def test_the_old_candidates_of_the_named_sites_come_with_their_pictures(
        self, tmp_path: Path
    ) -> None:
        old = _pool_run(tmp_path)
        sites, missing = PL.pool_sites(old, {"a"})
        assert [s["site_id"] for s in sites] == ["a"]
        (candidate,) = sites[0]["candidates"]
        assert candidate["file"] == "Here.jpg" and Path(candidate["path"]).is_file()
        assert candidate["route"] == "name"
        assert missing == [{"site_id": "a", "file": "Gone.jpg"}]  # named, never skipped

    def test_a_site_outside_the_population_is_left_out(self, tmp_path: Path) -> None:
        assert PL.pool_sites(_pool_run(tmp_path), {"zzz"}) == ([], [])

    def test_the_picture_path_is_where_the_old_download_kept_it(self, tmp_path: Path) -> None:
        old = _pool_run(tmp_path)
        path = PL.picture_path(old, {"picture_url": "https://thumb.wikimedia.org/h.jpg"})
        assert path.parent == old / "pictures" and len(path.name) == 32 and path.is_file()

    def test_the_old_targets_become_picks_with_the_old_judge_s_note(self, tmp_path: Path) -> None:
        old = _pool_run(tmp_path)
        population = [
            {
                "site_id": "a",
                "name": "Site a",
                "country": "Italy",
                "lat": 1.0,
                "lon": 2.0,
                "qid": "Q9",
            }
        ]
        (pick,) = PL.target_picks(old, population)
        assert (pick["file"], pick["note"], pick["answered_by"]) == (
            "Here.jpg",
            "the tomb",
            "mcode-judge-1",
        )
        assert Path(pick["path"]).is_file() and pick["picture_url"].endswith("h.jpg")

    def test_a_target_whose_picture_is_gone_is_refused_by_name(self, tmp_path: Path) -> None:
        old = _pool_run(tmp_path)
        for f in (old / "pictures").iterdir():
            f.unlink()
        with pytest.raises(PL.PoolError, match="is gone"):
            PL.target_picks(old, [{"site_id": "a", "name": "n", "lat": 1, "lon": 2}])

    def test_a_target_of_a_site_outside_the_population_is_refused(self, tmp_path: Path) -> None:
        with pytest.raises(PL.PoolError, match="no site, candidate or verdict"):
            PL.target_picks(_pool_run(tmp_path), [])

    def _old(self) -> list[dict[str, Any]]:
        return [
            {"site_id": "a", "file": f, "verdict": "depicts"}
            for f in ("p.jpg", "q.jpg", "r.jpg", "s.jpg")
        ]

    def test_what_claude_does_not_confirm_is_denied_with_the_reason(self) -> None:
        pre = [
            {
                "site_id": "a",
                "file": "p.jpg",
                "survives": False,
                "kind": "map_or_document",
                "answered_by": "pf",
            },
            {
                "site_id": "a",
                "file": "q.jpg",
                "survives": True,
                "kind": "site_photo",
                "answered_by": "pf",
            },
            {
                "site_id": "a",
                "file": "r.jpg",
                "survives": True,
                "kind": "site_photo",
                "answered_by": "pf",
            },
            {
                "site_id": "a",
                "file": "s.jpg",
                "survives": True,
                "kind": "site_photo",
                "answered_by": "pf",
            },
        ]
        dep = [
            {
                "site_id": "a",
                "file": "q.jpg",
                "verdict": "other_site",
                "note": "a coin",
                "answered_by": "dp",
            },
            {
                "site_id": "a",
                "file": "r.jpg",
                "verdict": "depicts",
                "note": "the tomb",
                "answered_by": "dp",
            },
            {
                "site_id": "a",
                "file": "s.jpg",
                "verdict": "depicts",
                "note": "the wall",
                "answered_by": "dp",
            },
        ]
        rck = [
            {
                "verdict": "other_site",
                "shows": "a wall of another town",
                "answered_by": "adversarial:rck-01-001",
                "meta": {"site_id": "a", "file": "s.jpg"},
            }
        ]
        got = PL.denied_pairs(self._old(), pre, dep, rck, {"a"})
        assert [(d["file"], d["verdict"]) for d in got] == [
            ("p.jpg", "not usable (map_or_document)"),
            ("q.jpg", "other_site"),
            ("s.jpg", "rejected by the re-check"),
        ]
        assert got[2]["shows"] == "a wall of another town"

    def test_a_pair_claude_has_not_judged_yet_is_an_error(self) -> None:
        with pytest.raises(PL.PoolError, match="Claude has not judged it"):
            PL.denied_pairs(self._old()[:1], [], [], [], {"a"})

    def test_only_a_pair_minimax_called_depicts_can_be_denied(self) -> None:
        old = [{"site_id": "a", "file": "p.jpg", "verdict": "other_site"}]
        assert PL.denied_pairs(old, [], [], [], {"a"}) == []

    def test_a_written_hero_outside_the_pool_is_judged_by_its_recheck_alone(self) -> None:
        """The 178 written heroes sit at sites that serve a picture now: no prefilter row, no depicts
        row, and not an error - the re-check is their only judge."""
        old = [{"site_id": "a", "file": f, "verdict": "depicts"} for f in ("w.jpg", "x.jpg")]
        rck = [
            {
                "verdict": verdict,
                "shows": "a coin",
                "answered_by": "adversarial:rck-01-001",
                "meta": {"site_id": "a", "file": file},
            }
            for file, verdict in (("w.jpg", "other_site"), ("x.jpg", "depicts"))
        ]
        got = PL.denied_pairs(old, [], [], rck, set())
        assert [(d["file"], d["verdict"]) for d in got] == [("w.jpg", "rejected by the re-check")]

    def test_a_depicts_the_claude_role_confirmed_needs_no_recheck_to_stay_undenied(self) -> None:
        dep = [
            {"site_id": "a", "file": "p.jpg", "verdict": "depicts", "note": "n", "answered_by": "d"}
        ]
        assert PL.denied_pairs(self._old()[:1], [], dep, [], {"a"}) == []

    def test_a_denied_pair_is_a_hero_only_where_the_page_serves_it(self, tmp_path: Path) -> None:
        run = tmp_path / "run"
        run.mkdir()
        data = {
            "read_at": "2026-10-09T00:00:00Z",
            "sites": [{"id": "a", "name": "n", "country": "c", "site_type": "t", "lat": 1, "lon": 2, "thumbnail_url": None}],
            "images": [
                {"id": 5, "site_id": "a", "filename": "p.webp", "title": "p", "original_url": "https://upload.wikimedia.org/wikipedia/commons/a/ab/P.jpg", "commons_page_url": None, "is_hero": True, "is_lead": False, "is_excluded": False, "sort_order": 0, "file_size_bytes": 1},
                {"id": 6, "site_id": "a", "filename": "q.webp", "title": "q", "original_url": "https://upload.wikimedia.org/wikipedia/commons/a/ab/Q.jpg", "commons_page_url": None, "is_hero": False, "is_lead": False, "is_excluded": False, "sort_order": 1, "file_size_bytes": 1},
            ],
            "retired": [],
        }  # fmt: skip
        ST.write_read(run / "READ.json", data)
        state = ST.load_read(run / "READ.json")
        denied = [
            {
                "site_id": "a",
                "file": "P.jpg",
                "verdict": "other_site",
                "shows": "a coin",
                "answered_by": "dp",
            },
            {
                "site_id": "a",
                "file": "Q.jpg",
                "verdict": "other_site",
                "shows": "a coin",
                "answered_by": "dp",
            },
        ]
        got = PL.denied_heroes(state, denied)
        assert [(h["image_id"], h["site_id"], h["stage"], h["verdict"]) for h in got] == [
            (5, "a", "image-depicts", "other_site")
        ]  # row 6 is no hero: the page does not serve it

    def test_a_live_hero_is_a_hero_row_that_is_not_excluded(self, tmp_path: Path) -> None:
        run = tmp_path / "run"
        run.mkdir()

        def row(image_id: int, file: str, **over: Any) -> dict[str, Any]:
            return {
                "id": image_id, "site_id": "a", "filename": f"{image_id}.webp", "title": file,
                "original_url": f"https://upload.wikimedia.org/wikipedia/commons/a/ab/{file}",
                "commons_page_url": None, "is_hero": True, "is_lead": False,
                "is_excluded": False, "sort_order": 0, "file_size_bytes": 1,
            } | over  # fmt: skip

        data = {
            "read_at": "2026-10-09T00:00:00Z",
            "sites": [{"id": "a", "name": "n", "country": "c", "site_type": "t", "lat": 1, "lon": 2, "thumbnail_url": None}],
            "images": [
                row(1, "Live.jpg"),
                row(2, "Hidden.jpg", is_excluded=True),
                row(3, "Plain.jpg", is_hero=False),
            ],
            "retired": [],
        }  # fmt: skip
        ST.write_read(run / "READ.json", data)
        state = ST.load_read(run / "READ.json")
        assert PL.live_hero_files(state) == {"a": {"Live.jpg"}}
        assert PL.state_record(state, "a") == {
            "site_id": "a", "name": "n", "country": "c", "site_type": "t", "lat": 1, "lon": 2,
        }  # fmt: skip
