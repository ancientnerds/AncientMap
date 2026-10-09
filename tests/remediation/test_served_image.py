"""WD2's served-image lane (O6): the read, the pre-check, the two vision stages, the plan.

DB-less and offline: production's read is a fixture READ.json, WD1's harvest a fixture in its fixed
layout (`SITES.jsonl` + `entities/<QID>.json`), Commons an `httpx.MockTransport`, the pictures
fixed bytes, and every Opus answer is written through `opus_handoff.write_answer` into a
temporary handoff. The ids and names of the fixture sites are production's where a case was
measured there (2026-09-26).
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import httpx
import pytest

REPO = Path(__file__).resolve().parents[2]
for _p in (REPO, REPO / "scripts" / "remediation"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import opus_handoff as OH  # noqa: E402
import research_web  # noqa: E402
from gallery_audit import chunk_writer as CW  # noqa: E402
from served_image import commons as C  # noqa: E402
from served_image import mcode_driver as D  # noqa: E402
from served_image import no_image_report as NR  # noqa: E402
from served_image import plan as PL  # noqa: E402
from served_image import precheck as PC  # noqa: E402
from served_image import state as ST  # noqa: E402
from served_image import vision as V  # noqa: E402

from pipeline.studio import mcode  # noqa: E402

THASOS = "33d2d754-e50a-4305-beff-87d2ad2c0227"
HABU = "0088c7e5-4a78-4b89-945d-3d5c787818e5"
BARE = "5b36f014-cb4a-4c2f-84b3-80996c503702"
HOTLINK = "026dfe16-5509-47f2-bede-504b006d704d"
NOTHING = "2dab79e8-1ece-4f9b-beb3-a91573d545c3"
RETIRED_SITE = "c8d2c13e-fd9a-466c-9fdc-fc26ee798ded"
BROKEN_THUMB = (
    "https://upload.wikimedia.org/wikipedia/commons/thumb/4/48/Rag-i_Bibi_relief.jpg/"
    "400px-Rag-i_Bibi_relief.jpg"
)
BIBI_INFO = {
    "status": "ok",
    "title": "Rag-i Bibi relief.jpg",
    "url": "https://upload.wikimedia.org/wikipedia/commons/4/48/Rag-i_Bibi_relief.jpg",
    "render_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/4/48/Rag-i_Bibi_relief.jpg/1280px-Rag-i_Bibi_relief.jpg",
    "mime": "image/jpeg",
}
#: Three files of a site's Commons category, as `categorymembers` (`cmtype=file`) lists them: a
#: TIFF (a still image Commons renders as JPEG), a PDF (rendered too: its first page) and a sound,
#: whose `thumburl` is Commons' file-type icon (read on 2026-09-26 for an MP3 and a FLAC).
TIFF = "Thasos plan.tif"
PDF = "Thasos guide.pdf"
OGG = "Thasos song.ogg"
MEMBER_INFO = {
    TIFF: {
        "status": "ok",
        "title": TIFF,
        "url": "https://upload.wikimedia.org/wikipedia/commons/7/7a/Thasos_plan.tif",
        "render_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/7/7a/Thasos_plan.tif/lossy-page1-1280px-Thasos_plan.tif.jpg",
        "mime": "image/tiff",
    },
    PDF: {
        "status": "ok",
        "title": PDF,
        "url": "https://upload.wikimedia.org/wikipedia/commons/5/5b/Thasos_guide.pdf",
        "render_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/5/5b/Thasos_guide.pdf/page1-1280px-Thasos_guide.pdf.jpg",
        "mime": "application/pdf",
    },
    OGG: {
        "status": "ok",
        "title": OGG,
        "url": "https://upload.wikimedia.org/wikipedia/commons/3/3c/Thasos_song.ogg",
        "render_url": "https://commons.wikimedia.org/w/resources/assets/file-type-icons/fileicon-ogg.png",
        "mime": "audio/ogg",
    },
}


def _commons(name: str) -> dict[str, str]:
    under = name.replace(" ", "_")
    return {
        "original_url": f"https://upload.wikimedia.org/wikipedia/commons/a/ab/{under}",
        "commons_page_url": f"https://commons.wikimedia.org/wiki/File%3A{under}",
    }


def row(
    image_id: int,
    site_id: str,
    name: str,
    *,
    hero: bool = False,
    lead: bool = False,
    excluded: bool = False,
    order: int = 0,
    size: int = 1000,
) -> dict[str, Any]:
    return {
        "id": image_id,
        "site_id": site_id,
        "filename": "hero.webp" if hero else name.replace(" ", "_").rsplit(".", 1)[0] + ".webp",
        "title": name,
        **_commons(name),
        "is_hero": hero,
        "is_lead": lead,
        "is_excluded": excluded,
        "sort_order": order,
        "file_size_bytes": size,
    }


def site(site_id: str, name: str, thumb: str | None = None) -> dict[str, Any]:
    return {
        "id": site_id,
        "name": name,
        "country": "Greece",
        "site_type": "City/town/settlement",
        "lat": 40.78,
        "lon": 24.71,
        "thumbnail_url": thumb,
    }


def read_fixture() -> dict[str, Any]:
    """Five sites: Thasos (hero is an island photo, two more rows), Medinet Habu (hero confirmed,
    thumbnail a hotlink), a site without an item, a thumbnail-only hotlink site, and one that
    serves nothing."""
    return {
        "read_at": "2026-09-26T02:00:00Z",
        "sites": [
            site(HOTLINK, "Rag-i Bibi", "https://example.org/relief.jpg"),
            site(HABU, "Medinet Habu", "https://upload.wikimedia.org/x.jpg"),
            site(THASOS, "Archaeological Site of Ancient Thasos", None),
            site(NOTHING, "Ahu Akivi", None),
            site(BARE, "Klopot", "/data/images/wiki/5b36f014/hero.webp"),
        ],
        "images": [
            row(1, THASOS, "Thasos.jpg", hero=True, lead=True),
            row(2, THASOS, "Thasos agora.jpg", order=1),
            row(3, THASOS, "Thasos theatre.jpg", order=2),
            row(4, THASOS, "Old excluded.jpg", excluded=True, order=3),
            row(10, HABU, "Medinet Habu on West Bank in Luxor Egypt.jpg", hero=True, lead=True),
            row(11, HABU, "Habu court.jpg", order=1),
            row(20, BARE, "Informacni panel.jpg", hero=True, lead=True),
        ],
        "retired": [RETIRED_SITE],
    }


def write_read(run: Path, data: dict[str, Any] | None = None) -> ST.State:
    run.mkdir(parents=True, exist_ok=True)
    ST.write_read(run / "READ.json", data or read_fixture())
    return ST.load_read(run / "READ.json")


def entity(qid: str, *, p18: list[str] = (), p373: list[str] = ()) -> dict[str, Any]:  # type: ignore[assignment]
    def claim(value: str, rank: str = "normal") -> dict[str, Any]:
        return {"mainsnak": {"datavalue": {"value": value}}, "rank": rank}

    return {
        "id": qid,
        "claims": {
            "P18": [claim(v) for v in p18] + [claim("Deprecated.jpg", "deprecated")],
            "P373": [claim(v) for v in p373],
        },
    }


def write_harvest(root: Path, qids: dict[str, str | None], entities: list[dict[str, Any]]) -> None:
    (root / "entities").mkdir(parents=True, exist_ok=True)
    lines = [
        json.dumps(
            {
                "site_id": sid,
                "name": "x",
                "country": "y",
                "lat": 0.0,
                "lon": 0.0,
                "qid": qid,
                "enwiki_title": None,
                "source_url": None,
            }
        )
        for sid, qid in qids.items()
    ]
    (root / "SITES.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
    for e in entities:
        (root / "entities" / f"{e['id']}.json").write_text(json.dumps(e), encoding="utf-8")


HARVEST_QIDS = {HOTLINK: None, HABU: "Q1", THASOS: "Q2", NOTHING: "Q3", BARE: "Q4"}
HARVEST_ENTITIES = [
    entity("Q1", p18=["Medinet Habu on West Bank in Luxor Egypt.jpg"]),
    entity("Q2", p18=["Thasos.jpg"], p373=["Thasos (ancient city)"]),
    entity("Q3"),
    entity("Q4", p373=["Kłopot, Lubusz Voivodeship"]),
]


class FakeCommons:
    """The three Commons questions, answered from dictionaries - no network."""

    def __init__(
        self,
        cats: dict[str, list[str]] | None = None,
        members: dict[str, list[str]] | None = None,
        info: dict[str, dict[str, Any]] | None = None,
    ) -> None:
        self.cats = cats or {}
        self.member_map = members or {}
        self.info = info or {}

    def categories(self, files: Any) -> dict[str, C.FileInfo]:
        out = {}
        for f in {ST.canonical_file(x) for x in files}:
            if f in self.cats:
                out[f] = C.FileInfo(C.OK, f, tuple(self.cats[f]))
            else:
                out[f] = C.FileInfo(C.MISSING, None, ())
        return out

    def members(self, category: str, limit: int) -> list[str]:
        return self.member_map.get(category, [])[:limit]

    def imageinfo(self, files: Any) -> dict[str, dict[str, Any]]:
        return {
            f: self.info.get(f, {"status": C.MISSING})
            for f in {ST.canonical_file(x) for x in files}
        }


class FakePictures:
    def __init__(self, commons: Any, gone: dict[str, str] | None = None) -> None:
        self.commons = commons
        self.gone = gone or {}
        self.asked: list[Any] = []

    def gallery(self, site_id: str, image_row: Any) -> bytes:
        self.asked.append(("gallery", int(image_row["id"])))
        return f"jpeg-row-{image_row['id']}".encode()

    def url(self, url: str) -> bytes:
        self.asked.append(("url", url))
        if url in self.gone:
            raise C.Unfetchable(self.gone[url])
        return f"jpeg-url-{url}".encode()


# ================================================================================== the read
class TestTheServedImage:
    def test_canonical_file_is_mediawiki_s_title_form(self) -> None:
        assert ST.canonical_file("File:thasos__agora_2.jpg") == "Thasos agora 2.jpg"
        assert ST.canonical_file(" Stonehenge.jpg ") == "Stonehenge.jpg"
        with pytest.raises(ST.StateError):
            ST.canonical_file("File: ")

    @pytest.mark.parametrize(
        ("url", "file"),
        [
            (
                "https://upload.wikimedia.org/wikipedia/commons/thumb/7/7c/Shah_Ji.jpg/400px-Shah_Ji.jpg",
                "Shah Ji.jpg",
            ),
            (
                "https://upload.wikimedia.org/wikipedia/commons/c/ce/Vall%C3%A9e.merveilles.JPG",
                "Vallée.merveilles.JPG",
            ),
            ("https://commons.wikimedia.org/wiki/File%3AMedinet%20Habu.jpg", "Medinet Habu.jpg"),
            ("https://en.wikipedia.org/wiki/Palenque#/media/File:Temple.jpg", None),
            ("/data/images/wiki/5b36f014/hero.webp", None),
            ("https://www.megalithic.co.uk/a/640px-x.jpg", None),
            (None, None),
        ],
    )
    def test_file_of_url(self, url: str | None, file: str | None) -> None:
        assert ST.file_of_url(url) == file

    def test_the_page_serves_the_hero_then_the_lead_then_the_order(self, tmp_path: Path) -> None:
        state = write_read(tmp_path / "run")
        served = ST.served_of(state.sites[THASOS], state.rows[THASOS])
        assert (served.kind, served.image_id, served.file) == (ST.GALLERY, 1, "Thasos.jpg")
        assert served.url == "/data/images/wiki/33d2d754/hero.webp"
        assert [r["id"] for r in ST.live_rows(state.rows[THASOS])] == [1, 2, 3]

    def test_a_site_without_a_live_row_serves_its_thumbnail(self, tmp_path: Path) -> None:
        data = read_fixture()
        for r in data["images"]:
            if r["site_id"] == BARE:
                r["is_excluded"] = True
                r["is_hero"] = False
        state = write_read(tmp_path / "run", data)
        served = ST.served_of(state.sites[BARE], state.rows[BARE])
        assert (served.kind, served.image_id, served.file) == (
            ST.THUMBNAIL,
            20,
            "Informacni panel.jpg",
        )
        hot = ST.served_of(state.sites[HOTLINK], ())
        assert (hot.kind, hot.image_id, hot.file) == (ST.THUMBNAIL, None, None)
        assert ST.served_of(state.sites[NOTHING], ()).kind == ST.NONE

    def test_a_read_is_written_once(self, tmp_path: Path) -> None:
        write_read(tmp_path / "run")
        with pytest.raises(ST.StateError, match="never replaced"):
            ST.write_read(tmp_path / "run" / "READ.json", read_fixture())

    def test_a_row_of_a_site_the_read_does_not_hold_is_refused(self, tmp_path: Path) -> None:
        data = read_fixture()
        data["images"].append(row(99, "00000000-0000-0000-0000-000000000000", "x.jpg"))
        (tmp_path / "READ.json").write_text(json.dumps(data), encoding="utf-8")
        with pytest.raises(ST.StateError, match="does not hold"):
            ST.load_read(tmp_path / "READ.json")

    def test_a_site_both_shown_and_retired_is_refused(self, tmp_path: Path) -> None:
        data = read_fixture()
        data["retired"] = [THASOS]
        with pytest.raises(ST.StateError, match="both shown and retired"):
            write_read(tmp_path / "run", data)

    def test_the_read_selects_the_shown_curated_sites_and_every_row(self) -> None:
        assert "u.scope_status = 'retired'" in ST.RETIRED_SQL
        assert "u.scope_status IS DISTINCT FROM 'retired'" in ST.SITES_SQL
        assert "u.source_id = 'ancient_nerds'" in ST.IMAGES_SQL
        assert "w.file_size_bytes" in ST.IMAGES_SQL
        assert "is_excluded" in ST.IMAGES_SQL and "WHERE w.is_excluded" not in ST.IMAGES_SQL


# ================================================================================ the harvest
class TestTheHarvest:
    def test_wd1_s_layout_is_read(self, tmp_path: Path) -> None:
        write_harvest(tmp_path, HARVEST_QIDS, HARVEST_ENTITIES)
        harvest = PC.load_harvest(tmp_path)
        assert harvest.qids[HOTLINK] is None
        assert PC.p18_files(harvest.entity("Q2")) == ["Thasos.jpg"]
        assert PC.p373_categories(harvest.entity("Q4")) == ["Kłopot, Lubusz Voivodeship"]

    def test_a_line_in_another_shape_is_refused(self, tmp_path: Path) -> None:
        (tmp_path / "SITES.jsonl").write_text(json.dumps({"site_id": HABU}) + "\n", "utf-8")
        with pytest.raises(PC.HarvestError, match="keys"):
            PC.load_harvest(tmp_path)

    def test_a_site_listed_twice_or_a_bad_qid_is_refused(self, tmp_path: Path) -> None:
        write_harvest(tmp_path, {HABU: "Q1"}, [])
        text = (tmp_path / "SITES.jsonl").read_text(encoding="utf-8")
        (tmp_path / "SITES.jsonl").write_text(text + text, encoding="utf-8")
        with pytest.raises(PC.HarvestError, match="twice"):
            PC.load_harvest(tmp_path)
        write_harvest(tmp_path, {HABU: "P31"}, [])
        with pytest.raises(PC.HarvestError, match="no Wikidata item id"):
            PC.load_harvest(tmp_path)

    def test_an_entity_file_must_hold_its_item(self, tmp_path: Path) -> None:
        write_harvest(tmp_path, {HABU: "Q1"}, [entity("Q9")])
        (tmp_path / "entities" / "Q9.json").rename(tmp_path / "entities" / "Q1.json")
        with pytest.raises(PC.HarvestError, match="not Q1"):
            PC.load_harvest(tmp_path).entity("Q1")
        merged = entity("Q9") | {"redirects": {"from": "Q1", "to": "Q9"}}
        (tmp_path / "entities" / "Q1.json").write_text(json.dumps(merged), encoding="utf-8")
        assert PC.load_harvest(tmp_path).entity("Q1")["id"] == "Q9"
        with pytest.raises(PC.HarvestError, match="holds no entity"):
            PC.load_harvest(tmp_path).entity("Q2")


# =============================================================================== the pre-check
def _served(kind: str = ST.GALLERY, file: str | None = "Thasos.jpg") -> ST.Served:
    return ST.Served(THASOS, kind, 1 if kind == ST.GALLERY else None, file, "/data/x")


class TestThePrecheck:
    def test_the_item_s_image_confirms(self) -> None:
        got = PC.decide(
            _served(), "Q2", entity("Q2", p18=["Thasos.jpg"]), C.FileInfo(C.OK, "Thasos.jpg", ())
        )
        assert got.status == PC.CONFIRMED_P18

    def test_a_renamed_file_confirms_under_its_new_title(self) -> None:
        info = C.FileInfo(C.OK, "Thasos new.jpg", ())
        got = PC.decide(_served(), "Q2", entity("Q2", p18=["Thasos new.jpg"]), info)
        assert got.status == PC.CONFIRMED_P18

    def test_direct_membership_in_the_item_s_category_confirms(self) -> None:
        info = C.FileInfo(C.OK, "Thasos.jpg", ("Thasos (ancient city)", "CC-BY-3.0"))
        got = PC.decide(_served(), "Q2", entity("Q2", p373=["Thasos (ancient city)"]), info)
        assert got.status == PC.CONFIRMED_P373 and "Thasos (ancient city)" in got.reason

    def test_a_subcategory_does_not_confirm(self) -> None:
        """Membership is direct: the file sits in a subcategory of the item's category."""
        info = C.FileInfo(C.OK, "Thasos.jpg", ("Satellite pictures of Thasos",))
        got = PC.decide(_served(), "Q2", entity("Q2", p373=["Thasos"]), info)
        assert got.status == PC.UNCONFIRMED

    @pytest.mark.parametrize(
        ("served", "qid", "ent", "info", "reason"),
        [
            (_served(), None, None, None, "no Wikidata item"),
            (_served(), "Q2", {"id": "Q2", "missing": ""}, None, "holds no item"),
            (_served(file=None), "Q2", entity("Q2", p18=["Thasos.jpg"]), None, "names no Commons"),
            (_served(), "Q2", entity("Q2", p373=["X"]), C.FileInfo(C.MISSING, None, ()), "missing"),
            (
                _served(),
                "Q2",
                entity("Q2"),
                C.FileInfo(C.OK, "Thasos.jpg", ("X",)),
                "names no image",
            ),
        ],
    )
    def test_everything_else_is_unconfirmed(
        self, served: ST.Served, qid: Any, ent: Any, info: Any, reason: str
    ) -> None:
        got = PC.decide(served, qid, ent, info)
        assert got.status == PC.UNCONFIRMED and reason in got.reason

    def test_a_site_that_serves_nothing_is_no_image(self) -> None:
        assert PC.decide(_served(ST.NONE, None), "Q2", None, None).status == PC.NO_IMAGE

    def test_the_run_covers_the_read_or_names_a_subset(self, tmp_path: Path) -> None:
        state = write_read(tmp_path / "run")
        write_harvest(tmp_path / "h", {HABU: "Q1"}, HARVEST_ENTITIES)
        with pytest.raises(PC.HarvestError, match="not in the harvest"):
            PC.run_precheck(state, PC.load_harvest(tmp_path / "h"), FakeCommons())
        result = PC.run_precheck(
            state,
            PC.load_harvest(tmp_path / "h"),
            FakeCommons({"Medinet Habu on West Bank in Luxor Egypt.jpg": []}),
            subset=True,
        )
        assert [c.site_id for c in result.checks] == [HABU]
        assert result.counts()[PC.CONFIRMED_P18] == 1 and result.counts()["not_in_harvest"] == 4

    def test_the_pre_check_is_written_once(self, tmp_path: Path) -> None:
        """Re-run after WD1 re-harvests, it would change the qids behind every later stage."""
        state = write_read(tmp_path / "run")
        write_harvest(tmp_path / "h", {HABU: "Q1"}, HARVEST_ENTITIES)
        commons = FakeCommons({"Medinet Habu on West Bank in Luxor Egypt.jpg": []})
        result = PC.run_precheck(state, PC.load_harvest(tmp_path / "h"), commons, subset=True)
        PC.write_prechecks(tmp_path / "run" / PC.PRECHECK_FILE, result)
        with pytest.raises(ST.StateError, match="never replaced"):
            PC.write_prechecks(tmp_path / "run" / PC.PRECHECK_FILE, result)

    def test_a_harvest_of_every_curated_site_lists_the_retired_ones_too(
        self, tmp_path: Path
    ) -> None:
        """WD1's harvest covers all 5,004 curated sites; the read shows 4,926. The 78 retired
        are known to the read and pass; a site it does not know at all is refused."""
        state = write_read(tmp_path / "run")
        qids = dict(HARVEST_QIDS)
        write_harvest(tmp_path / "h", qids | {RETIRED_SITE: None}, HARVEST_ENTITIES)
        commons = FakeCommons(
            {
                "Medinet Habu on West Bank in Luxor Egypt.jpg": [],
                "Thasos.jpg": [],
                "Informacni panel.jpg": [],
            }
        )
        result = PC.run_precheck(state, PC.load_harvest(tmp_path / "h"), commons)
        assert len(result.checks) == 5 and result.counts()["not_in_harvest"] == 0
        stranger = "11111111-1111-4111-8111-111111111111"
        write_harvest(tmp_path / "h2", qids | {stranger: None}, HARVEST_ENTITIES)
        with pytest.raises(PC.HarvestError, match="neither shows nor knows as retired"):
            PC.run_precheck(state, PC.load_harvest(tmp_path / "h2"), commons)


# ================================================================================ Commons
def _client(handler: Any) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler), headers=research_web.HEADERS)


class TestCommons:
    def test_the_user_agent_names_no_person(self) -> None:
        assert "@" not in research_web.USER_AGENT
        assert research_web.USER_AGENT.startswith("AncientMapRemediation/1.0 (research")

    def test_categories_follow_continuation_normalisation_and_missing(self, tmp_path: Path) -> None:
        calls: list[dict[str, str]] = []

        def handler(request: httpx.Request) -> httpx.Response:
            form = dict(httpx.QueryParams(request.content.decode()))
            calls.append(form)
            assert request.method == "POST"
            assert request.headers["User-Agent"] == research_web.USER_AGENT
            pages = [
                {"title": "File:Thasos.jpg", "categories": [{"title": "Category:Thasos"}]},
                {"title": "File:Gone.jpg", "missing": True},
            ]
            if "clcontinue" not in form:
                return httpx.Response(
                    200,
                    json={
                        "continue": {"clcontinue": "x", "continue": "||"},
                        "query": {
                            "redirects": [{"from": "File:Thasos old.jpg", "to": "File:Thasos.jpg"}],
                            "pages": pages,
                        },
                    },
                )
            more = [{"title": "File:Thasos.jpg", "categories": [{"title": "Category:Islands"}]}]
            return httpx.Response(200, json={"query": {"pages": more}})

        commons = C.Commons(tmp_path, _client(handler), pace=0)
        got = commons.categories(["Thasos_old.jpg", "Gone.jpg"])
        assert got["Thasos old.jpg"] == C.FileInfo(C.OK, "Thasos.jpg", ("Islands", "Thasos"))
        assert got["Gone.jpg"].status == C.MISSING
        assert len(calls) == 2
        commons.categories(["Gone.jpg"])  # cached: no third request
        assert len(calls) == 2

    def test_a_refused_query_raises(self, tmp_path: Path) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"error": {"code": "maxlag"}})

        with pytest.raises(C.CommonsError, match="refused"):
            C.Commons(tmp_path, _client(handler), pace=0).categories(["A.jpg"])

    def test_imageinfo_drops_the_tracking_query(self, tmp_path: Path) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            info = {
                "url": "https://upload.wikimedia.org/wikipedia/commons/6/6b/T.jpg?utm_source=x",
                "thumburl": "https://thumb.wikimedia.org/.../1280px-T.jpg?utm_campaign=y",
            }
            return httpx.Response(
                200, json={"query": {"pages": [{"title": "File:T.jpg", "imageinfo": [info]}]}}
            )

        got = C.Commons(tmp_path, _client(handler), pace=0).imageinfo(["T.jpg"])["T.jpg"]
        assert got["url"] == "https://upload.wikimedia.org/wikipedia/commons/6/6b/T.jpg"
        assert got["render_url"] == "https://thumb.wikimedia.org/.../1280px-T.jpg"
        assert (
            C.RENDER_WIDTH
            in __import__("pipeline.wiki_image_downloader").wiki_image_downloader.COMMONS_BUCKETS
        )

    def test_a_file_without_a_rendering_has_no_render_url(self, tmp_path: Path) -> None:
        """An answer without `thumburl`: the original is never taken for a rendering."""

        def handler(request: httpx.Request) -> httpx.Response:
            info = {
                "url": "https://upload.wikimedia.org/wikipedia/commons/a/ab/T.jpg",
                "mime": "image/jpeg",
            }
            page = {"title": "File:T.jpg", "imageinfo": [info]}
            return httpx.Response(200, json={"query": {"pages": [page]}})

        got = C.Commons(tmp_path, _client(handler), pace=0).imageinfo(["T.jpg"])["T.jpg"]
        assert got["render_url"] is None and C.picture_url(got) is None

    def test_a_sound_s_icon_is_no_picture(self) -> None:
        """A sound's `thumburl` is Commons' file-type icon: the MIME type decides, not the URL."""
        assert MEMBER_INFO[OGG]["render_url"] and C.picture_url(MEMBER_INFO[OGG]) is None

    @pytest.mark.parametrize(
        ("mime", "render", "shown"),
        [
            ("image/jpeg", "https://u/1280px-A.jpg", True),
            ("image/png", "https://u/1280px-A.png", True),
            ("image/tiff", "https://u/lossy-page1-1280px-A.tif.jpg", True),
            ("image/svg+xml", "https://u/1280px-A.svg.png", True),
            ("application/pdf", "https://u/page1-1280px-A.pdf.jpg", False),
            ("image/vnd.djvu", "https://u/page1-1280px-A.djvu.jpg", False),
            ("video/webm", "https://u/1280px--A.webm.jpg", False),
            ("audio/mpeg", "https://c/file-type-icons/fileicon-ogg.png", False),
            ("image/jpeg", None, False),
        ],
    )
    def test_a_picture_is_a_still_image_with_its_rendering(
        self, mime: str, render: str | None, shown: bool
    ) -> None:
        info = {
            "status": C.OK,
            "title": "A",
            "url": "https://u/A",
            "render_url": render,
            "mime": mime,
        }
        assert C.picture_url(info) == (render if shown else None)
        assert C.picture_url({"status": C.MISSING}) is None

    @pytest.mark.parametrize("status", [403, 404, 410])
    def test_a_gone_address_is_unfetchable(self, tmp_path: Path, status: int) -> None:
        commons = C.Commons(tmp_path, _client(lambda r: httpx.Response(status)), pace=0)
        with pytest.raises(C.Unfetchable):
            commons.download("https://example.org/a.jpg")

    def test_a_refused_connection_is_unfetchable(self, tmp_path: Path) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("reset", request=request)

        with pytest.raises(C.Unfetchable):
            C.Commons(tmp_path, _client(handler), pace=0).download("https://example.org/a.jpg")

    @pytest.mark.parametrize("status", [429, 500, 503])
    def test_a_busy_host_stops_the_command(self, tmp_path: Path, status: int) -> None:
        commons = C.Commons(tmp_path, _client(lambda r: httpx.Response(status)), pace=0)
        with pytest.raises(C.CommonsError) as info:
            commons.download("https://example.org/a.jpg")
        assert not isinstance(info.value, C.Unfetchable)

    def test_a_private_address_is_never_fetched(self, tmp_path: Path) -> None:
        commons = C.Commons(tmp_path, _client(lambda r: httpx.Response(200, content=b"x")), pace=0)
        with pytest.raises(C.CommonsError, match="never fetched"):
            commons.download("http://127.0.0.1/a.jpg")

    def test_a_download_is_kept_once(self, tmp_path: Path) -> None:
        hits: list[int] = []

        def handler(request: httpx.Request) -> httpx.Response:
            hits.append(1)
            return httpx.Response(200, content=b"bytes")

        commons = C.Commons(tmp_path, _client(handler), pace=0)
        first = commons.download("https://example.org/a.jpg")
        assert commons.download("https://example.org/a.jpg") == first and len(hits) == 1


# ================================================================================ the answers
class TestTheAnswers:
    def test_the_frozen_prompts(self) -> None:
        """Changing a prompt makes every answer stale: re-pin only with a new prompt id."""
        assert V.CHECK_PROMPT_ID == "served-check-v1"
        assert V.REPLACE_PROMPT_ID == "served-replace-v2"
        assert V.prompt_sha256(V.CHECK_PROMPT) == CHECK_PIN
        assert V.prompt_sha256(V.REPLACE_PROMPT) == REPLACE_PIN

    def test_a_check_answer_in_shape(self) -> None:
        got = V.parse_check('{"verdict": "region_or_type", "shows": "island", "basis": "NASA"}')
        assert got == {"verdict": "region_or_type", "shows": "island", "basis": "NASA"}

    @pytest.mark.parametrize(
        ("text", "problem"),
        [
            ("no json", "no JSON"),
            ('{"verdict": "yes", "shows": "a", "basis": "b"}', "not one of"),
            ('{"verdict": "depicts", "shows": "a"}', "carries"),
            ('{"verdict": "depicts", "shows": "", "basis": "b"}', "non-empty"),
            ('{"verdict": "depicts", "shows": "a", "basis": "b", "x": 1}', "carries"),
        ],
    )
    def test_a_check_answer_out_of_shape(self, text: str, problem: str) -> None:
        with pytest.raises(V.AnswerError, match=problem):
            V.parse_check(text)

    def _question(self) -> V.ReplaceQuestion:
        def cand(label: str, kind: str) -> V.Candidate:
            return V.Candidate(
                label, kind, 2 if kind == "gallery" else None, "f.jpg", "w", None, "i", "s"
            )

        return V.ReplaceQuestion(
            "replace-001", THASOS, "T", "Greece", "x", 0.0, 0.0, "Q2", {}, "region_or_type", "i",
            (cand("G1", V.GALLERY_CANDIDATE), cand("G2", V.GALLERY_CANDIDATE), cand("W1", V.COMMONS_CANDIDATE)),
        )  # fmt: skip

    def _answer(self, verdicts: dict[str, str], pick: str | None) -> str:
        return json.dumps({"candidates": verdicts, "pick": pick, "basis": "seen"})

    def test_a_replace_answer_in_shape(self) -> None:
        q = self._question()
        v = {"G1": "depicts", "G2": "other_site", "W1": "depicts"}
        assert V.parse_replace(self._answer(v, "G1"), q)["pick"] == "G1"
        v = {"G1": "region_or_type", "G2": "other_site", "W1": "depicts"}
        assert V.parse_replace(self._answer(v, "W1"), q)["pick"] == "W1"
        v = {"G1": "region_or_type", "G2": "other_site", "W1": "other_site"}
        assert V.parse_replace(self._answer(v, None), q)["pick"] is None

    @pytest.mark.parametrize(
        ("verdicts", "pick", "problem"),
        [
            ({"G1": "depicts", "G2": "other_site"}, "G1", "exactly"),
            ({"G1": "depicts", "G2": "maybe", "W1": "depicts"}, "G1", "not one of"),
            ({"G1": "depicts", "G2": "other_site", "W1": "depicts"}, None, "null"),
            (
                {"G1": "region_or_type", "G2": "other_site", "W1": "depicts"},
                "G1",
                "not a candidate",
            ),
            ({"G1": "depicts", "G2": "other_site", "W1": "depicts"}, "W1", "G candidates"),
        ],
    )
    def test_a_replace_answer_out_of_shape(
        self, verdicts: dict[str, str], pick: str | None, problem: str
    ) -> None:
        with pytest.raises(V.AnswerError, match=problem):
            V.parse_replace(self._answer(verdicts, pick), self._question())


CHECK_PIN = "a96ac7880303e3855c634ee5afb006f23eb04e215029f299d79f9bb61d25497b"
#: v1 (65e0c88b...) asked only about a served image the check rejected; the 2026-09-30 run's
#: answers and their recorded prompt hashes carry it, in that run's own files. v2 adds the opening
#: for a site that serves no image, where there is no verdict to report and no gallery to pick.
REPLACE_PIN = "a570ebaa2ba32e03fd41caf6ed4d7fb2b93b715d2f7dd9037806b85f4adada86"


# ================================================================================ the stages
def _setup(
    tmp_path: Path,
    *,
    gone: dict[str, str] | None = None,
    read: dict[str, Any] | None = None,
    info: dict[str, dict[str, Any]] | None = None,
    members: list[str] | None = None,
) -> tuple[Path, Path, Any]:
    run = tmp_path / "served-image-2026-09-26"
    state = write_read(run, read)
    write_harvest(tmp_path / "harvest", HARVEST_QIDS, HARVEST_ENTITIES)
    fake = FakeCommons(
        cats={
            "Thasos.jpg": ["Satellite pictures of Thasos"],
            "Medinet Habu on West Bank in Luxor Egypt.jpg": ["Medinet Habu temple complex"],
            "Informacni panel.jpg": ["Kłopot, Lubusz Voivodeship"],
        },
        members={
            "Thasos (ancient city)": members
            or ["Thasos agora.jpg", "Thasos gate.jpg", "Thasos.jpg"]
        },
        info={"Thasos gate.jpg": GATE_INFO, **(info or {})},
    )
    result = PC.run_precheck(state, PC.load_harvest(tmp_path / "harvest"), fake)
    PC.write_prechecks(run / PC.PRECHECK_FILE, result)
    (run / "PRECHECK.json").write_text(
        json.dumps({"read_sha256": state.sha256, "harvest": str(tmp_path / "harvest")}), "utf-8"
    )
    pictures = FakePictures(fake, gone=gone)
    return run, tmp_path / "handoff-check", pictures


GATE_INFO = {
    "status": C.OK,
    "title": "Thasos gate.jpg",
    "url": "https://upload.wikimedia.org/wikipedia/commons/1/12/Thasos_gate.jpg",
    "render_url": "https://thumb.wikimedia.org/1280px-Thasos_gate.jpg",
    "mime": "image/jpeg",
}
#: A Commons file an item claims as its image (P18) for a site that serves none.
RUIN_INFO = {
    "status": C.OK,
    "title": "Ruin.jpg",
    "url": "https://upload.wikimedia.org/wikipedia/commons/9/9a/Ruin.jpg",
    "render_url": "https://thumb.wikimedia.org/1280px-Ruin.jpg",
    "mime": "image/jpeg",
}


def _answer_all(
    handoff: Path, stage: str, answers: dict[str, str], model: str = OH.OPUS_MODEL
) -> None:
    for line in OH.manifest(handoff):
        OH.write_answer(
            handoff,
            model=model,
            batch_id=line["batch_id"],
            stage=stage,
            label=line["label"],
            text=answers[line["label"]],
            answered_by=line["batch_id"],
            now=lambda: "2026-09-26T03:00:00+00:00",
        )


def _check(verdict: str) -> str:
    return json.dumps({"verdict": verdict, "shows": "something", "basis": "the picture"})


@pytest.mark.parametrize("stamp", [OH.OPUS_MODEL, OH.SONNET_MODEL])
def test_the_import_stores_the_stamp_of_the_model_that_answered(tmp_path: Path, stamp: str) -> None:
    """A record of who judged names the answer's own model (owner decision 2026-10-01: the
    answering subagents run Sonnet), never a constant; a mechanical line names none."""
    run, _ = TestTheStages()._full(
        tmp_path, {HABU: V.DEPICTS, THASOS: V.REGION_OR_TYPE, BARE: V.REGION_OR_TYPE}, stamp
    )
    got = {r["site_id"]: r for r in V.read_jsonl(run / V.CHECK)}
    assert {got[s]["model"] for s in (HABU, THASOS, BARE)} == {stamp}
    assert got[HOTLINK]["model"] is None


class TestTheStages:
    def test_every_served_image_is_asked_by_default(self, tmp_path: Path) -> None:
        run, handoff, pictures = _setup(tmp_path, gone={"https://example.org/relief.jpg": "404"})
        state = ST.load_read(run / "READ.json")
        pre = PC.load_prechecks(run / "PRECHECK.jsonl")
        assert pre[HABU]["status"] == PC.CONFIRMED_P18  # asked all the same
        got = V.export_check(run, handoff, state, pre, pictures)
        assert got["questions"] == 3 and got["unfetchable"] == 1
        labels = {line["label"] for line in OH.manifest(handoff)}
        assert labels == {HABU, THASOS, BARE}
        assert ("gallery", 1) in pictures.asked and ("gallery", 10) in pictures.asked

    def test_the_original_design_asks_only_the_unconfirmed(self, tmp_path: Path) -> None:
        run, handoff, pictures = _setup(tmp_path)
        state = ST.load_read(run / "READ.json")
        pre = PC.load_prechecks(run / "PRECHECK.jsonl")
        got = V.export_check(run, handoff, state, pre, pictures, population=V.UNCONFIRMED_ONLY)
        # Thasos's island photo is the item's P18: the original design never asks about it
        assert pre[THASOS]["status"] == PC.CONFIRMED_P18
        assert {line["label"] for line in OH.manifest(handoff)} == {HOTLINK}
        assert got["questions"] == 1

    def test_twelve_per_batch(self, tmp_path: Path) -> None:
        run, handoff, pictures = _setup(tmp_path)
        state = ST.load_read(run / "READ.json")
        pre = PC.load_prechecks(run / "PRECHECK.jsonl")
        with pytest.raises(ST.StateError, match="1..12"):
            V.export_check(run, handoff, state, pre, pictures, per_batch=13)
        V.export_check(run, handoff, state, pre, pictures, per_batch=2)
        batches = sorted({line["batch_id"] for line in OH.manifest(handoff)})
        assert batches == ["check-001", "check-002"]

    def _full(
        self, tmp_path: Path, verdicts: dict[str, str], model: str = OH.OPUS_MODEL, **setup: Any
    ) -> tuple[Path, Any]:
        return _full_run(tmp_path, verdicts, model, **setup)

    def test_a_site_that_serves_nothing_is_asked_about_the_files_its_item_claims(
        self, tmp_path: Path
    ) -> None:
        """A site with no image is never in the check stage, so without this its Wikidata item's
        P18/P373 files are never looked at - the gap that leaves an addressable site unserved."""
        run, pictures = self._full(tmp_path, {HABU: V.DEPICTS, THASOS: V.DEPICTS, BARE: V.DEPICTS})
        _claim(pictures, tmp_path)
        state = ST.load_read(run / "READ.json")
        pre = PC.load_prechecks(run / "PRECHECK.jsonl")
        got = V.export_replace(
            run, tmp_path / "ho", state, pre, PC.load_harvest(tmp_path / "harvest"), pictures
        )
        assert got["claimed"] == 1 and got["questions"] == 1
        [question] = V.read_jsonl(run / V.QUESTIONS_REPLACE)
        assert question["site_id"] == NOTHING
        assert [c["label"] for c in question["candidates"]] == ["W1"]
        assert question["candidates"][0]["url"] == RUIN_INFO["render_url"]
        # the prompt must not state a verdict nobody gave
        prompt = V.ReplaceQuestion.from_json(question).prompt()
        assert "serves no image" in prompt and "was judged" not in prompt

    def test_a_site_that_serves_nothing_and_claims_nothing_is_not_asked(
        self, tmp_path: Path
    ) -> None:
        run, pictures = self._full(tmp_path, {HABU: V.DEPICTS, THASOS: V.DEPICTS, BARE: V.DEPICTS})
        state = ST.load_read(run / "READ.json")
        pre = PC.load_prechecks(run / "PRECHECK.jsonl")
        got = V.export_replace(
            run, tmp_path / "ho", state, pre, PC.load_harvest(tmp_path / "harvest"), pictures
        )
        assert got["claimed"] == 0 and got["questions"] == 0

    def test_the_plan_refuses_while_a_claimed_site_is_unanswered(self, tmp_path: Path) -> None:
        run, pictures = self._full(tmp_path, {HABU: V.DEPICTS, THASOS: V.DEPICTS, BARE: V.DEPICTS})
        _claim(pictures, tmp_path)
        state = ST.load_read(run / "READ.json")
        pre = PC.load_prechecks(run / "PRECHECK.jsonl")
        V.export_replace(
            run, tmp_path / "ho", state, pre, PC.load_harvest(tmp_path / "harvest"), pictures
        )
        with pytest.raises(ST.StateError, match="no replacement answer"):
            PL.write_plan(run)

    def test_a_claimed_file_reaches_the_plan_through_the_whole_stage(self, tmp_path: Path) -> None:
        run, pictures = self._full(tmp_path, {HABU: V.DEPICTS, THASOS: V.DEPICTS, BARE: V.DEPICTS})
        _claim(pictures, tmp_path)
        state = ST.load_read(run / "READ.json")
        pre = PC.load_prechecks(run / "PRECHECK.jsonl")
        handoff = tmp_path / "handoff-replace"
        V.export_replace(run, handoff, state, pre, PC.load_harvest(tmp_path / "harvest"), pictures)
        _answer_all(
            handoff,
            V.STAGE_REPLACE,
            {
                NOTHING: json.dumps(
                    {"candidates": {"W1": "depicts"}, "pick": "W1", "basis": "the ruin"}
                )
            },
        )
        V.import_stage(run, V.STAGE_REPLACE)
        PL.write_plan(run)
        expected = {
            e["site_id"]: e
            for e in map(json.loads, (run / "chunks" / "EXPECTED.jsonl").read_text().splitlines())
        }
        assert expected[NOTHING] == {
            "site_id": NOTHING,
            "outcome": "claimed",
            "served_image_id": None,
            "thumbnail_url": RUIN_INFO["render_url"],
            "chunk": 1,
        }
        # the site has no image row, so no gallery row moves
        [row] = V.read_jsonl(run / V.REPLACE)
        assert row["site_id"] == NOTHING and row["pick"] == "W1"

    def test_the_brief_of_a_claim_batch_names_the_model_and_the_case(self, tmp_path: Path) -> None:
        run, pictures = self._full(tmp_path, {HABU: V.DEPICTS, THASOS: V.DEPICTS, BARE: V.DEPICTS})
        _claim(pictures, tmp_path)
        state = ST.load_read(run / "READ.json")
        pre = PC.load_prechecks(run / "PRECHECK.jsonl")
        handoff = tmp_path / "handoff-replace"
        V.export_replace(run, handoff, state, pre, PC.load_harvest(tmp_path / "harvest"), pictures)
        text = V.brief(run, handoff, "replace-001")
        assert f"running as {V.ANSWER_MODEL}" in text
        assert "a site that serves no image at all" in text
        assert "You are Opus agent" not in text

    def test_the_claim_export_stands_alone_without_the_check_stage(self, tmp_path: Path) -> None:
        """A run that only closes the goal's gap needs no check stage: the 2026-09-30 run already
        judged the served images and is in production. The record must say so, and the plan must
        leave every site that serves an image exactly as it is."""
        run, _, pictures = _setup(tmp_path, gone={"https://example.org/relief.jpg": "404"})
        _claim(pictures, tmp_path)
        state = ST.load_read(run / "READ.json")
        pre = PC.load_prechecks(run / "PRECHECK.jsonl")
        got = V.export_replace(
            run,
            tmp_path / "ho",
            state,
            pre,
            PC.load_harvest(tmp_path / "harvest"),
            pictures,
            claimed_only=True,
        )
        assert got == {
            "failed": 0,
            "claimed": 1,
            "questions": 1,
            "without_candidates": 0,
            "batches": 1,
        }
        record = json.loads((run / V.EXPORT_REPLACE).read_text(encoding="utf-8"))
        assert record["claimed_only"] is True and record["check_sha256"] is None
        handoff = tmp_path / "ho"
        _answer_all(
            handoff,
            V.STAGE_REPLACE,
            {
                NOTHING: json.dumps(
                    {"candidates": {"W1": "depicts"}, "pick": "W1", "basis": "the ruin"}
                )
            },
        )
        V.import_stage(run, V.STAGE_REPLACE)
        PL.write_plan(run)
        [row] = V.read_jsonl(run / V.REPLACE)
        assert row["site_id"] == NOTHING and row["prompt_sha256"] == V.prompt_sha256(
            V.ReplaceQuestion.from_json([*V.read_jsonl(run / V.QUESTIONS_REPLACE)][0]).prompt()
        )
        # every site that serves an image is left exactly as it is, and says so
        plans, summary = PL.build(run)
        assert [p.site_id for p in plans if p.changes] == [NOTHING]
        assert all(p.outcome == PL.UNJUDGED for p in plans if p.site_id != NOTHING)
        assert summary["population"] == V.CLAIMED_ONLY

    def test_the_claim_export_is_refused_while_a_check_failed(self, tmp_path: Path) -> None:
        """A run whose served images were judged and failed must export the failures too - a
        claim-only export would plan those sites as "no image" and empty them."""
        run, pictures = self._full(
            tmp_path, {HABU: V.DEPICTS, THASOS: V.REGION_OR_TYPE, BARE: V.DEPICTS}
        )
        _claim(pictures, tmp_path)
        state = ST.load_read(run / "READ.json")
        pre = PC.load_prechecks(run / "PRECHECK.jsonl")
        with pytest.raises(ST.StateError, match="export the failed images too"):
            V.export_replace(
                run,
                tmp_path / "ho",
                state,
                pre,
                PC.load_harvest(tmp_path / "harvest"),
                pictures,
                claimed_only=True,
            )

    def test_the_import_records_every_answer_and_the_unfetchable(self, tmp_path: Path) -> None:
        run, _ = self._full(
            tmp_path, {HABU: V.DEPICTS, THASOS: V.REGION_OR_TYPE, BARE: V.REGION_OR_TYPE}
        )
        got = {r["site_id"]: r for r in V.read_jsonl(run / V.CHECK)}
        assert got[THASOS]["verdict"] == V.REGION_OR_TYPE
        assert got[THASOS]["answered_by"] == "check-001"
        assert got[HOTLINK]["verdict"] == V.UNFETCHABLE and "404" in got[HOTLINK]["basis"]

    def _broken_thumbnail(
        self, tmp_path: Path, *, file_known: bool, mime: str = "image/jpeg"
    ) -> tuple[Path, Path, Any]:
        """Rag-i Bibi serves only its thumbnail, a Commons rendering at a width Commons no longer
        renders (HTTP 400, as all 262 such thumbnails on 2026-09-26)."""
        read = read_fixture()
        read["sites"][0]["thumbnail_url"] = BROKEN_THUMB
        info = {"Rag-i Bibi relief.jpg": BIBI_INFO | {"mime": mime}} if file_known else {}
        return _setup(tmp_path, read=read, gone={BROKEN_THUMB: "HTTP 400"}, info=info)

    def test_a_thumbnail_whose_address_is_broken_is_checked_through_its_file(
        self, tmp_path: Path
    ) -> None:
        run, handoff, pictures = self._broken_thumbnail(tmp_path, file_known=True)
        state = ST.load_read(run / "READ.json")
        got = V.export_check(
            run, handoff, state, PC.load_prechecks(run / "PRECHECK.jsonl"), pictures
        )
        assert got["unfetchable"] == 0 and got["questions"] == 4
        assert ("url", BIBI_INFO["render_url"]) in pictures.asked
        [question] = [q for q in V.read_jsonl(run / V.QUESTIONS_CHECK) if q["site_id"] == HOTLINK]
        assert question["repair"] == {
            "render_url": BIBI_INFO["render_url"],
            "stored_url": BROKEN_THUMB,
            "error": "HTTP 400",
        }
        assert question["source"] == BIBI_INFO["render_url"]

    def test_a_broken_thumbnail_whose_file_is_gone_has_no_picture(self, tmp_path: Path) -> None:
        run, handoff, pictures = self._broken_thumbnail(tmp_path, file_known=False)
        state = ST.load_read(run / "READ.json")
        got = V.export_check(
            run, handoff, state, PC.load_prechecks(run / "PRECHECK.jsonl"), pictures
        )
        assert got["unfetchable"] == 1 and got["questions"] == 3

    def test_a_broken_thumbnail_whose_file_is_no_picture_has_no_picture(
        self, tmp_path: Path
    ) -> None:
        run, handoff, pictures = self._broken_thumbnail(
            tmp_path, file_known=True, mime="application/pdf"
        )
        state = ST.load_read(run / "READ.json")
        got = V.export_check(
            run, handoff, state, PC.load_prechecks(run / "PRECHECK.jsonl"), pictures
        )
        assert got["unfetchable"] == 1 and ("url", BIBI_INFO["render_url"]) not in pictures.asked

    def test_a_depicting_file_behind_a_broken_thumbnail_repairs_the_address(
        self, tmp_path: Path
    ) -> None:
        run, handoff, pictures = self._broken_thumbnail(tmp_path, file_known=True)
        state = ST.load_read(run / "READ.json")
        V.export_check(run, handoff, state, PC.load_prechecks(run / "PRECHECK.jsonl"), pictures)
        _answer_all(handoff, V.STAGE_CHECK, {sid: _check(V.DEPICTS) for sid in state.sites})
        V.import_stage(run, V.STAGE_CHECK)
        checks = {r["site_id"]: r for r in V.read_jsonl(run / V.CHECK)}
        plan = PL.decide_site(
            state.sites[HOTLINK], (), PC.load_prechecks(run / "PRECHECK.jsonl")[HOTLINK],
            checks[HOTLINK], None, population=V.ALL,
        )  # fmt: skip
        # the rendering the agent saw (a standard 1280 bucket), not the original's many MB
        assert (plan.outcome, plan.thumbnail_url) == (PL.CONFIRMED, BIBI_INFO["render_url"])
        [change] = plan.changes
        assert (change.column, change.old_value, change.new_value, change.rule) == (
            "thumbnail_url",
            BROKEN_THUMB,
            BIBI_INFO["render_url"],
            PL.RULE_THUMB,
        )
        assert "HTTP 400" in change.reason
        CW.validate_change(change)

    def test_the_import_refuses_an_unanswered_handoff(self, tmp_path: Path) -> None:
        run, handoff, pictures = _setup(tmp_path)
        state = ST.load_read(run / "READ.json")
        V.export_check(run, handoff, state, PC.load_prechecks(run / "PRECHECK.jsonl"), pictures)
        with pytest.raises(ST.StateError, match="does not validate"):
            V.import_stage(run, V.STAGE_CHECK)

    def test_the_import_refuses_a_changed_picture(self, tmp_path: Path) -> None:
        run, handoff, pictures = _setup(tmp_path)
        state = ST.load_read(run / "READ.json")
        V.export_check(run, handoff, state, PC.load_prechecks(run / "PRECHECK.jsonl"), pictures)
        _answer_all(
            handoff, V.STAGE_CHECK, {s: _check(V.DEPICTS) for s in (HABU, THASOS, BARE, HOTLINK)}
        )
        (handoff / "images" / f"check-{THASOS}.jpg").write_bytes(b"another picture")
        with pytest.raises(ST.StateError, match="not the picture"):
            V.import_stage(run, V.STAGE_CHECK)

    def test_check_answer_and_brief(self, tmp_path: Path) -> None:
        run, handoff, pictures = _setup(tmp_path)
        state = ST.load_read(run / "READ.json")
        V.export_check(run, handoff, state, PC.load_prechecks(run / "PRECHECK.jsonl"), pictures)
        assert V.check_answer(run, handoff, "check-001", THASOS, _check(V.DEPICTS)) is None
        assert "not one of" in (
            V.check_answer(run, handoff, "check-001", THASOS, _check("x")) or ""
        )
        with pytest.raises(ST.StateError, match="no question"):
            V.check_answer(run, handoff, "check-009", THASOS, _check(V.DEPICTS))
        text = V.brief(run, handoff, "check-001")
        assert "--stage served-check" in text and "Read tool" in text and "4 question(s)" in text
        assert (
            "--model <the model id you run as: claude-sonnet-5-5>" in text
        )  # an agent names the model it runs as (owner decision D6, 2026-10-08: Claude only)
        assert (
            V.ANSWER_MODEL in OH.NEW_ANSWER_MODELS
        )  # the recorder must accept what the brief names
        assert "You are Opus agent" not in text  # the vision answers are the image_depicts role's

    def test_the_candidates_of_a_failed_image(self, tmp_path: Path) -> None:
        """G: the other live rows in page order; W: P18 and P373 files the gallery lacks, each once,
        without the failed file; a file Commons does not hold is not shown."""
        run, _ = self._full(tmp_path, {HABU: V.DEPICTS, THASOS: V.REGION_OR_TYPE, BARE: V.DEPICTS})
        state = ST.load_read(run / "READ.json")
        pre = PC.load_prechecks(run / "PRECHECK.jsonl")
        found, unavailable = V.candidates_for(
            state, pre[THASOS], PC.load_harvest(tmp_path / "harvest"), _setup_commons()
        )
        assert [(c["kind"], c.get("row", {}).get("id"), c.get("file")) for c in found] == [
            (V.GALLERY_CANDIDATE, 2, None),
            (V.GALLERY_CANDIDATE, 3, None),
            (V.COMMONS_CANDIDATE, None, "Thasos gate.jpg"),
        ]
        assert unavailable == []

    def test_a_candidate_is_a_still_picture_shown_as_its_rendering(self, tmp_path: Path) -> None:
        """`categorymembers` with `cmtype=file` lists every file: a TIFF is a candidate, shown as
        its JPEG rendering; a PDF and a sound are listed as no picture, never shown."""
        run, _ = self._full(tmp_path, {HABU: V.DEPICTS, THASOS: V.REGION_OR_TYPE, BARE: V.DEPICTS})
        state = ST.load_read(run / "READ.json")
        pre = PC.load_prechecks(run / "PRECHECK.jsonl")
        commons = FakeCommons(members={"Thasos (ancient city)": [TIFF, PDF, OGG]}, info=MEMBER_INFO)
        found, unavailable = V.candidates_for(
            state, pre[THASOS], PC.load_harvest(tmp_path / "harvest"), commons
        )
        w = [c for c in found if c["kind"] == V.COMMONS_CANDIDATE]
        assert [(c["file"], c["picture_url"]) for c in w] == [
            (TIFF, MEMBER_INFO[TIFF]["render_url"])
        ]
        assert unavailable == [
            {"file": PDF, "why": 'in the site\'s Commons category "Thasos (ancient city)" (P373)',
             "status": V.NOT_A_PICTURE, "detail": "application/pdf"},
            {"file": OGG, "why": 'in the site\'s Commons category "Thasos (ancient city)" (P373)',
             "status": V.NOT_A_PICTURE, "detail": "audio/ogg"},
        ]  # fmt: skip

    def test_a_commons_pick_stores_the_rendering_the_agent_saw(self, tmp_path: Path) -> None:
        """A TIFF picked: the thumbnail becomes its JPEG rendering, which an <img> shows."""
        run, pictures = self._full(
            tmp_path,
            {HABU: V.DEPICTS, THASOS: V.REGION_OR_TYPE, BARE: V.DEPICTS},
            members=[TIFF, PDF, OGG],
            info=MEMBER_INFO,
        )
        state = ST.load_read(run / "READ.json")
        pre = PC.load_prechecks(run / "PRECHECK.jsonl")
        handoff = tmp_path / "handoff-replace"
        V.export_replace(run, handoff, state, pre, PC.load_harvest(tmp_path / "harvest"), pictures)
        assert ("url", MEMBER_INFO[TIFF]["render_url"]) in pictures.asked
        record = json.loads((run / V.EXPORT_REPLACE).read_text(encoding="utf-8"))
        assert [u["file"] for u in record["unavailable"][THASOS]] == [PDF, OGG]
        [question] = V.read_jsonl(run / V.QUESTIONS_REPLACE)
        assert question["candidates"][-1]["url"] == MEMBER_INFO[TIFF]["render_url"]
        answer = json.dumps(
            {
                "candidates": {"G1": "other_site", "G2": "region_or_type", "W1": "depicts"},
                "pick": "W1",
                "basis": "the plan of the site",
            }
        )
        _answer_all(handoff, V.STAGE_REPLACE, {THASOS: answer})
        V.import_stage(run, V.STAGE_REPLACE)
        PL.write_plan(run)
        expected = {
            e["site_id"]: e
            for e in map(json.loads, (run / "chunks" / "EXPECTED.jsonl").read_text().splitlines())
        }
        assert expected[THASOS]["outcome"] == PL.CLEARED
        assert expected[THASOS]["thumbnail_url"] == MEMBER_INFO[TIFF]["render_url"]

    def test_a_rendering_that_is_not_served_is_listed_not_fatal(self, tmp_path: Path) -> None:
        run, pictures = self._full(
            tmp_path, {HABU: V.DEPICTS, THASOS: V.REGION_OR_TYPE, BARE: V.DEPICTS}
        )
        pictures.gone[GATE_INFO["render_url"]] = "HTTP 404"
        state = ST.load_read(run / "READ.json")
        pre = PC.load_prechecks(run / "PRECHECK.jsonl")
        got = V.export_replace(
            run, tmp_path / "ho", state, pre, PC.load_harvest(tmp_path / "harvest"), pictures
        )
        assert got["questions"] == 1
        [question] = V.read_jsonl(run / V.QUESTIONS_REPLACE)
        assert [c["label"] for c in question["candidates"]] == ["G1", "G2"]
        record = json.loads((run / V.EXPORT_REPLACE).read_text(encoding="utf-8"))
        [gone] = record["unavailable"][THASOS]
        assert (gone["file"], gone["status"], gone["detail"]) == (
            "Thasos gate.jpg",
            V.UNFETCHABLE,
            "HTTP 404",
        )

    def test_a_check_without_questions_records_its_unfetchable_thumbnails(
        self, tmp_path: Path
    ) -> None:
        """Every served image an unfetchable thumbnail: no question, so no handoff - the import
        still records each one as `unfetchable`, for the replacement stage."""
        read = read_fixture()
        read["sites"] = [s for s in read["sites"] if s["id"] in (HOTLINK, NOTHING)]
        read["images"] = []
        read["retired"] += [HABU, THASOS, BARE]  # the harvest lists every curated site
        run, handoff, pictures = _setup(
            tmp_path, read=read, gone={"https://example.org/relief.jpg": "HTTP 404"}
        )
        state = ST.load_read(run / "READ.json")
        pre = PC.load_prechecks(run / PC.PRECHECK_FILE)
        got = V.export_check(run, handoff, state, pre, pictures)
        assert (got["questions"], got["unfetchable"]) == (0, 1) and not handoff.exists()
        assert V.import_stage(run, V.STAGE_CHECK)["counts"] == {V.UNFETCHABLE: 1}

    def test_an_export_that_asked_nothing_has_nothing_to_import(self, tmp_path: Path) -> None:
        run, pictures = self._full(tmp_path, {HABU: V.DEPICTS, THASOS: V.DEPICTS, BARE: V.DEPICTS})
        state = ST.load_read(run / "READ.json")
        pre = PC.load_prechecks(run / "PRECHECK.jsonl")
        got = V.export_replace(
            run, tmp_path / "ho", state, pre, PC.load_harvest(tmp_path / "harvest"), pictures
        )
        assert got["questions"] == 0 and got["without_candidates"] == 1
        with pytest.raises(ST.StateError, match="asked nothing"):
            V.import_stage(run, V.STAGE_REPLACE)
        assert PL.write_plan(run)["counts"]["cleared"] == 1  # the plan needs no import

    def test_a_pre_check_run_again_after_the_check_export_is_refused(self, tmp_path: Path) -> None:
        """EXPORT_CHECK pins the pre-check: one rewritten since (WD1 re-harvested into the same
        directory) would change the qids behind the candidates and the plan's evidence."""
        run, pictures = self._full(
            tmp_path, {HABU: V.DEPICTS, THASOS: V.REGION_OR_TYPE, BARE: V.DEPICTS}
        )
        record = json.loads((run / V.EXPORT_CHECK).read_text(encoding="utf-8"))
        assert record["precheck_sha256"] == ST.file_sha256(run / PC.PRECHECK_FILE)
        path = run / PC.PRECHECK_FILE
        path.write_text(path.read_text(encoding="utf-8").replace('"Q2"', '"Q9"'), "utf-8")
        state = ST.load_read(run / "READ.json")
        with pytest.raises(ST.StateError, match="not the pre-check"):
            V.export_replace(
                run, tmp_path / "ho", state, PC.load_prechecks(path),
                PC.load_harvest(tmp_path / "harvest"), pictures,
            )  # fmt: skip
        with pytest.raises(ST.StateError, match="not the pre-check"):
            PL.build(run)

    def test_replace_export_import_and_plan(self, tmp_path: Path) -> None:
        run, pictures = self._full(
            tmp_path, {HABU: V.DEPICTS, THASOS: V.REGION_OR_TYPE, BARE: V.REGION_OR_TYPE}
        )
        state = ST.load_read(run / "READ.json")
        pre = PC.load_prechecks(run / "PRECHECK.jsonl")
        handoff = tmp_path / "handoff-replace"
        got = V.export_replace(
            run, handoff, state, pre, PC.load_harvest(tmp_path / "harvest"), pictures
        )
        # Thasos: G1, G2, W1; Klopot: no other row, no P18/P373 file -> no candidates;
        # the hotlink site: no item -> no candidates
        assert got == {
            "failed": 3,
            "claimed": 0,
            "questions": 1,
            "without_candidates": 2,
            "batches": 1,
        }
        answer = json.dumps(
            {
                "candidates": {"G1": "depicts", "G2": "other_site", "W1": "depicts"},
                "pick": "G1",
                "basis": "the agora",
            }
        )
        _answer_all(handoff, V.STAGE_REPLACE, {THASOS: answer})
        V.import_stage(run, V.STAGE_REPLACE)
        summary = PL.write_plan(run)
        assert summary["counts"] == {
            "confirmed": 1,
            "replaced": 1,
            "cleared": 2,
            "no image": 1,
            "sites with a change": 4,
            "rows": 9,  # Thasos's G2, judged another site's picture, leaves the gallery
        }
        expected = {
            e["site_id"]: e
            for e in map(json.loads, (run / "chunks" / "EXPECTED.jsonl").read_text().splitlines())
        }
        assert expected[THASOS]["served_image_id"] == 2
        assert expected[THASOS]["thumbnail_url"] == "/data/images/wiki/33d2d754/Thasos_agora.webp"
        assert expected[BARE] | {"chunk": None} == {
            "site_id": BARE,
            "outcome": "cleared",
            "served_image_id": None,
            "thumbnail_url": None,
            "chunk": None,
        }
        chunk = CW.load_chunk(run / "chunks" / "chunk-001")
        assert chunk.lane.stamp == "served-image-2026-09-26"
        assert chunk.may_empty == frozenset({BARE})
        CW.check_delivered(run / "chunks" / "chunk-001")


def _setup_commons() -> FakeCommons:
    return FakeCommons(
        members={"Thasos (ancient city)": ["Thasos agora.jpg", "Thasos gate.jpg", "Thasos.jpg"]},
        info={"Thasos gate.jpg": GATE_INFO},
    )


# ================================================================================ the plan
def _claim(pictures: Any, root: Path, file: str = "Ruin.jpg") -> None:
    """Give the site that serves nothing (Q3) an image claim, and Commons an answer about it.

    The fixture's Q3 names no file, which is the 688+307 sites' measured case. The goal's
    population is the opposite: a site with no image whose own Wikidata item names one.
    """
    (root / "harvest" / "entities" / "Q3.json").write_text(
        json.dumps(entity("Q3", p18=[file])), encoding="utf-8"
    )
    pictures.commons.info[file] = RUIN_INFO | {"title": file}


def _pre(sid: str, status: str, served: ST.Served) -> dict[str, Any]:
    return {
        "site_id": sid,
        "status": status,
        "reason": "r",
        "qid": "Q2",
        "served": served.as_json(),
    }


def _checked(sid: str, verdict: str, served: ST.Served) -> dict[str, Any]:
    return {
        "site_id": sid,
        "verdict": verdict,
        "shows": "s",
        "basis": "b",
        "answered_by": "check-001",
        "prompt_sha256": "0" * 64,
        "served": served.as_json(),
        "repair": None,
    }


def _replaced(
    pick: str | None, verdicts: dict[str, str], shown: list[dict[str, Any]]
) -> dict[str, Any]:
    return {
        "pick": pick,
        "candidates": verdicts,
        "candidates_shown": shown,
        "basis": "b",
        "answered_by": "replace-001",
        "prompt_sha256": "1" * 64,
    }


def _thasos_state(tmp_path: Path) -> ST.State:
    return write_read(tmp_path / "run")


class TestThePlan:
    def test_a_confirmed_image_aligns_the_thumbnail(self, tmp_path: Path) -> None:
        state = _thasos_state(tmp_path)
        served = ST.served_of(state.sites[HABU], state.rows[HABU])
        plan = PL.decide_site(
            state.sites[HABU], state.rows[HABU], _pre(HABU, PC.UNCONFIRMED, served),
            _checked(HABU, V.DEPICTS, served), None, population=V.ALL,
        )  # fmt: skip
        assert plan.outcome == PL.CONFIRMED and plan.served_image_id == 10
        [change] = plan.changes
        assert (change.column, change.old_value, change.new_value, change.rule) == (
            "thumbnail_url",
            "https://upload.wikimedia.org/x.jpg",
            "/data/images/wiki/0088c7e5/hero.webp",
            PL.RULE_ALIGN,
        )
        CW.validate_change(change)

    def test_a_confirmed_image_with_its_thumbnail_changes_nothing(self, tmp_path: Path) -> None:
        data = read_fixture()
        data["sites"][1]["thumbnail_url"] = "/data/images/wiki/0088c7e5/hero.webp"
        state = write_read(tmp_path / "run", data)
        served = ST.served_of(state.sites[HABU], state.rows[HABU])
        plan = PL.decide_site(
            state.sites[HABU], state.rows[HABU], _pre(HABU, PC.CONFIRMED_P18, served),
            None, None, population=V.UNCONFIRMED_ONLY,
        )  # fmt: skip
        assert plan.changes == [] and plan.outcome == PL.CONFIRMED

    def test_without_a_check_answer_the_plan_refuses(self, tmp_path: Path) -> None:
        state = _thasos_state(tmp_path)
        served = ST.served_of(state.sites[HABU], state.rows[HABU])
        with pytest.raises(ST.StateError, match="no check answer"):
            PL.decide_site(
                state.sites[HABU], state.rows[HABU], _pre(HABU, PC.CONFIRMED_P18, served),
                None, None, population=V.ALL,
            )  # fmt: skip

    def test_a_gallery_pick_moves_the_hero(self, tmp_path: Path) -> None:
        state = _thasos_state(tmp_path)
        served = ST.served_of(state.sites[THASOS], state.rows[THASOS])
        shown = [
            {"label": "G1", "kind": V.GALLERY_CANDIDATE, "image_id": 2, "file": "a", "url": None},
            {"label": "G2", "kind": V.GALLERY_CANDIDATE, "image_id": 3, "file": "b", "url": None},
        ]
        plan = PL.decide_site(
            state.sites[THASOS], state.rows[THASOS], _pre(THASOS, PC.CONFIRMED_P18, served),
            _checked(THASOS, V.REGION_OR_TYPE, served),
            _replaced("G1", {"G1": "depicts", "G2": "other_site"}, shown), population=V.ALL,
        )  # fmt: skip
        cells = {(c.row_key, c.column, c.old_value, c.new_value) for c in plan.changes}
        assert cells == {
            ("1", "is_hero", "true", "false"),
            ("2", "is_hero", "false", "true"),
            ("3", "is_excluded", "false", "true"),  # G2: another site's picture
            (THASOS, "thumbnail_url", None, "/data/images/wiki/33d2d754/Thasos_agora.webp"),
        }
        assert plan.outcome == PL.REPLACED and plan.served_image_id == 2 and not plan.may_empty
        [excluded] = [c for c in plan.changes if c.column == "is_excluded"]
        assert excluded.evidence[-1]["verdict"] == V.OTHER_SITE and excluded.rule == PL.RULE_EXCLUDE
        for change in plan.changes:
            CW.validate_change(change)

    def test_a_gallery_pick_excludes_the_served_row_that_shows_another_site(
        self, tmp_path: Path
    ) -> None:
        """The served row the check called another site's picture leaves the gallery too; a
        region or landscape view stays in it below the new hero."""
        state = _thasos_state(tmp_path)
        served = ST.served_of(state.sites[THASOS], state.rows[THASOS])
        shown = [
            {"label": "G1", "kind": V.GALLERY_CANDIDATE, "image_id": 2, "file": "a", "url": None},
            {"label": "G2", "kind": V.GALLERY_CANDIDATE, "image_id": 3, "file": "b", "url": None},
        ]
        plan = PL.decide_site(
            state.sites[THASOS], state.rows[THASOS], _pre(THASOS, PC.UNCONFIRMED, served),
            _checked(THASOS, V.OTHER_SITE, served),
            _replaced("G1", {"G1": "depicts", "G2": "region_or_type"}, shown), population=V.ALL,
        )  # fmt: skip
        cells = {(c.row_key, c.column, c.old_value, c.new_value) for c in plan.changes}
        assert cells == {
            ("1", "is_hero", "true", "false"),
            ("1", "is_excluded", "false", "true"),
            ("2", "is_hero", "false", "true"),
            (THASOS, "thumbnail_url", None, "/data/images/wiki/33d2d754/Thasos_agora.webp"),
        }
        [excluded] = [c for c in plan.changes if c.column == "is_excluded"]
        assert excluded.evidence == [
            e for e in excluded.evidence if e["source"] == "served_image/CHECK.jsonl"
        ]

    def test_a_commons_pick_clears_the_gallery_and_points_the_thumbnail(
        self, tmp_path: Path
    ) -> None:
        state = _thasos_state(tmp_path)
        served = ST.served_of(state.sites[THASOS], state.rows[THASOS])
        url = GATE_INFO["render_url"]
        shown = [
            {"label": "G1", "kind": V.GALLERY_CANDIDATE, "image_id": 2, "file": "a", "url": None},
            {"label": "G2", "kind": V.GALLERY_CANDIDATE, "image_id": 3, "file": "b", "url": None},
            {"label": "W1", "kind": V.COMMONS_CANDIDATE, "image_id": None, "file": "Thasos gate.jpg", "url": url},
        ]  # fmt: skip
        plan = PL.decide_site(
            state.sites[THASOS], state.rows[THASOS], _pre(THASOS, PC.UNCONFIRMED, served),
            _checked(THASOS, V.OTHER_SITE, served),
            _replaced("W1", {"G1": "other_site", "G2": "region_or_type", "W1": "depicts"}, shown),
            population=V.ALL,
        )  # fmt: skip
        cells = {(c.row_key, c.column, c.new_value) for c in plan.changes}
        assert cells == {
            ("1", "is_hero", "false"),
            ("1", "is_excluded", "true"),
            ("2", "is_excluded", "true"),
            ("3", "is_excluded", "true"),
            (THASOS, "thumbnail_url", url),
        }
        assert plan.may_empty and plan.outcome == PL.CLEARED and plan.thumbnail_url == url
        for change in plan.changes:
            CW.validate_change(change)

    def test_no_pick_clears_to_no_image(self, tmp_path: Path) -> None:
        state = _thasos_state(tmp_path)
        served = ST.served_of(state.sites[BARE], state.rows[BARE])
        plan = PL.decide_site(
            state.sites[BARE], state.rows[BARE], _pre(BARE, PC.CONFIRMED_P373, served),
            _checked(BARE, V.REGION_OR_TYPE, served), None, population=V.ALL,
        )  # fmt: skip
        cells = {(c.row_key, c.column, c.new_value) for c in plan.changes}
        assert cells == {
            ("20", "is_hero", "false"),
            ("20", "is_excluded", "true"),
            (BARE, "thumbnail_url", None),
        }

    def test_a_claimed_file_serves_a_site_that_had_no_image(self, tmp_path: Path) -> None:
        """A site with no image row can only serve a Commons file: the popup and the detail page
        read `thumbnail_url` first, so the claimed file's rendering is the whole write."""
        state = _thasos_state(tmp_path)
        shown = [
            {
                "label": "W1",
                "kind": V.COMMONS_CANDIDATE,
                "image_id": None,
                "file": "Ruin.jpg",
                "url": RUIN_INFO["render_url"],
            }
        ]
        plan = PL.decide_site(
            state.sites[NOTHING],
            state.rows.get(NOTHING, ()),
            _pre(NOTHING, PC.NO_IMAGE, ST.served_of(state.sites[NOTHING], ())),
            None,
            _replaced("W1", {"W1": "depicts"}, shown),
            population=V.ALL,
        )  # fmt: skip
        [change] = plan.changes
        assert (change.column, change.old_value, change.new_value, change.rule) == (
            "thumbnail_url",
            None,
            RUIN_INFO["render_url"],
            PL.RULE_THUMB,
        )
        assert plan.outcome == PL.CLAIMED and not plan.may_empty
        assert change.evidence[-1]["verdict"] == V.DEPICTS
        CW.validate_change(change)

    def test_a_claimed_site_nothing_depicts_keeps_serving_no_image(self, tmp_path: Path) -> None:
        state = _thasos_state(tmp_path)
        shown = [
            {
                "label": "W1",
                "kind": V.COMMONS_CANDIDATE,
                "image_id": None,
                "file": "Ruin.jpg",
                "url": RUIN_INFO["render_url"],
            }
        ]
        plan = PL.decide_site(
            state.sites[NOTHING],
            state.rows.get(NOTHING, ()),
            _pre(NOTHING, PC.NO_IMAGE, ST.served_of(state.sites[NOTHING], ())),
            None,
            _replaced(None, {"W1": "region_or_type"}, shown),
            population=V.ALL,
        )  # fmt: skip
        assert plan.outcome == PL.NOTHING and plan.changes == [] and plan.thumbnail_url is None

    def test_a_claimed_site_the_export_asked_and_nobody_answered_is_refused(
        self, tmp_path: Path
    ) -> None:
        state = _thasos_state(tmp_path)
        with pytest.raises(ST.StateError, match="no replacement answer"):
            PL.decide_site(
                state.sites[NOTHING],
                state.rows.get(NOTHING, ()),
                _pre(NOTHING, PC.NO_IMAGE, ST.served_of(state.sites[NOTHING], ())),
                None,
                None,
                population=V.ALL,
                asked=True,
            )  # fmt: skip

    def test_a_site_with_no_image_row_cannot_pick_a_gallery_file(self, tmp_path: Path) -> None:
        state = _thasos_state(tmp_path)
        shown = [
            {"label": "G1", "kind": V.GALLERY_CANDIDATE, "image_id": 2, "file": "a", "url": None}
        ]
        with pytest.raises(ST.StateError, match="serves no gallery file"):
            PL.decide_site(
                state.sites[NOTHING],
                state.rows.get(NOTHING, ()),
                _pre(NOTHING, PC.NO_IMAGE, ST.served_of(state.sites[NOTHING], ())),
                None,
                _replaced("G1", {"G1": "depicts"}, shown),
                population=V.ALL,
            )  # fmt: skip

    def test_a_site_that_claims_nothing_is_left_alone(self, tmp_path: Path) -> None:
        state = _thasos_state(tmp_path)
        plan = PL.decide_site(
            state.sites[NOTHING],
            state.rows.get(NOTHING, ()),
            _pre(NOTHING, PC.NO_IMAGE, ST.served_of(state.sites[NOTHING], ())),
            None,
            None,
            population=V.ALL,
        )  # fmt: skip
        assert plan.outcome == PL.NOTHING and plan.changes == []

    def test_a_live_row_nobody_judged_is_never_excluded(self, tmp_path: Path) -> None:
        state = _thasos_state(tmp_path)
        served = ST.served_of(state.sites[THASOS], state.rows[THASOS])
        with pytest.raises(ST.StateError, match="neither checked nor shown"):
            PL.decide_site(
                state.sites[THASOS], state.rows[THASOS], _pre(THASOS, PC.UNCONFIRMED, served),
                _checked(THASOS, V.REGION_OR_TYPE, served), None, population=V.ALL,
            )  # fmt: skip

    def test_the_run_directory_names_the_journal_stamp(self, tmp_path: Path) -> None:
        assert (
            PL.lane_for(tmp_path / "served-image-2026-09-26b").stamp == "served-image-2026-09-26b"
        )
        with pytest.raises(ST.StateError, match="not a run directory"):
            PL.lane_for(tmp_path / "run")

    def test_a_named_run_names_the_journal_stamp_too(self, tmp_path: Path) -> None:
        """D15's run is `served-image-2026-10-08-os47`: the stamp is the directory's name."""
        lane = PL.lane_for(tmp_path / "served-image-2026-10-08-os47")
        assert lane.stamp == "served-image-2026-10-08-os47"
        for bad in (
            "served-image-2026-10-08-OS47",
            "served-image-2026-10-08-",
            "served-image-os47",
        ):
            with pytest.raises(ST.StateError, match="not a run directory"):
                PL.lane_for(tmp_path / bad)


def _full_run(
    tmp_path: Path, verdicts: dict[str, str], model: str = OH.OPUS_MODEL, **setup: Any
) -> tuple[Path, Any]:
    """A run through the check stage: the read, the pre-check, the export, the answers, the import."""
    run, handoff, pictures = _setup(
        tmp_path, gone={"https://example.org/relief.jpg": "404"}, **setup
    )
    state = ST.load_read(run / "READ.json")
    pre = PC.load_prechecks(run / "PRECHECK.jsonl")
    V.export_check(run, handoff, state, pre, pictures)
    _answer_all(handoff, V.STAGE_CHECK, {sid: _check(v) for sid, v in verdicts.items()}, model)
    V.import_stage(run, V.STAGE_CHECK)
    return run, pictures


# ================================================================================== the driver
class TestTheMcodeDriver:
    """One `mcode exec` run per question. No run here: the run is the CLI's, and this tests what
    the driver does with what a run produced - the prompt, the stamp, the record, the skip."""

    def _handoff(self, tmp_path: Path) -> tuple[Path, Path]:
        """A run whose check rejected one served image, so the replacement stage has one question."""
        run, pictures = _full_run(
            tmp_path, {HABU: V.DEPICTS, THASOS: V.REGION_OR_TYPE, BARE: V.DEPICTS}
        )
        state = ST.load_read(run / "READ.json")
        pre = PC.load_prechecks(run / "PRECHECK.jsonl")
        handoff = tmp_path / "ho"
        V.export_replace(run, handoff, state, pre, PC.load_harvest(tmp_path / "harvest"), pictures)
        return run, handoff

    def _answer(self, job: Any, verdicts: dict[str, str], pick: str | None) -> str:
        return json.dumps({"candidates": verdicts, "pick": pick, "basis": "the gate itself"})

    def test_the_prompt_names_the_question_the_pictures_and_the_answer_file(
        self, tmp_path: Path
    ) -> None:
        run, handoff = self._handoff(tmp_path)
        [job] = D.jobs(run, handoff)
        text = D.answer_prompt(job, D.check_command(run, handoff, job))
        assert job.prompt_path.as_posix() in text
        assert job.answer_path.as_posix() in text
        assert (
            f"run as {mcode.MODEL}" in text
        )  # this transport is MiniMax's, whatever the brief says
        assert "check-answer" in text and job.label in text
        assert not job.answer_path.exists()
        # the answer belongs beside the handoff, never inside the repository
        assert D.ROOT not in job.answer_path.parents

    def test_a_model_the_handoff_does_not_know_is_refused(self) -> None:
        with pytest.raises(ST.StateError, match="no key of opus_handoff.ANSWER_MODELS"):
            D.stamp_of("gpt-5.2")

    def test_the_answer_is_recorded_with_the_stamp_of_the_model_that_wrote_it(
        self, tmp_path: Path
    ) -> None:
        run, handoff = self._handoff(tmp_path)
        [job] = D.jobs(run, handoff)
        gallery = [c.label for c in job.question.candidates if c.kind == V.GALLERY_CANDIDATE]
        given = {c.label: V.OTHER_SITE for c in job.question.candidates}
        given[gallery[0]] = V.DEPICTS
        got = D.record(job, handoff, self._answer(job, given, gallery[0]), mcode.MODEL)
        assert got == {"label": job.label, "wrote": True, "pick": gallery[0]}
        answer = OH.read_answer(
            handoff,
            batch_id=job.batch_id,
            stage=job.stage,
            label=job.label,
            prompt=job.prompt_path.read_bytes().decode("utf-8"),
        )
        assert answer.model == OH.MINIMAX_MODEL
        assert answer.answered_by == f"mcode/{job.label[:8]}"
        # the question is answered now, so a second run does not ask it again
        assert D.jobs(run, handoff) == []
        assert D.jobs(run, handoff, labels=[job.label]) == []

    def test_an_answer_the_lane_refuses_is_not_recorded(self, tmp_path: Path) -> None:
        run, handoff = self._handoff(tmp_path)
        [job] = D.jobs(run, handoff)
        labels = [c.label for c in job.question.candidates]
        with pytest.raises(V.AnswerError):
            D.record(
                job,
                handoff,
                self._answer(job, dict.fromkeys(labels, "yes"), None),
                mcode.MODEL,
            )
        assert D.jobs(run, handoff) == [job]

    def test_a_commons_pick_is_refused_while_a_gallery_file_depicts(self, tmp_path: Path) -> None:
        """The lane's own rule, reached through the driver: only the gallery can become a page's
        image, so a W pick beside a G candidate called `depicts` is refused, not recorded."""
        run, handoff = self._handoff(tmp_path)
        [job] = D.jobs(run, handoff)
        commons = [c.label for c in job.question.candidates if c.kind == V.COMMONS_CANDIDATE]
        gallery = [c.label for c in job.question.candidates if c.kind == V.GALLERY_CANDIDATE]
        if not commons or not gallery:
            pytest.skip("this question has no Commons file beside a gallery file")
        given = {c.label: V.REGION_OR_TYPE for c in job.question.candidates}
        given[commons[0]] = V.DEPICTS
        given[gallery[0]] = V.DEPICTS
        with pytest.raises(V.AnswerError, match="G candidates"):
            D.record(job, handoff, self._answer(job, given, commons[0]), mcode.MODEL)
        assert D.jobs(run, handoff) == [job]


class TestTheAcceptance:
    def _expected(self) -> list[dict[str, Any]]:
        return [
            {"site_id": THASOS, "served_image_id": 2, "thumbnail_url": "/t"},
            {"site_id": BARE, "served_image_id": None, "thumbnail_url": None},
        ]

    def _sites(self, thumb: str | None = "/t") -> list[dict[str, Any]]:
        return [
            {"id": THASOS, "thumbnail_url": thumb, "source_id": "ancient_nerds"},
            {"id": BARE, "thumbnail_url": None, "source_id": "ancient_nerds"},
        ]

    def _rows(self) -> list[dict[str, Any]]:
        return [
            row(1, THASOS, "Thasos.jpg"),
            row(2, THASOS, "Thasos agora.jpg", hero=True),
            row(20, BARE, "Informacni panel.jpg", excluded=True),
        ]

    def test_production_as_planned_has_no_deviation(self) -> None:
        assert PL.deviations(self._expected(), self._sites(), self._rows()) == []

    def test_every_difference_is_named(self) -> None:
        rows = self._rows()
        rows[1]["is_hero"] = False
        rows[2]["is_excluded"] = False
        got = PL.deviations(self._expected(), self._sites(thumb="/other"), rows)
        assert any("serves image 1" in d for d in got)
        assert any("thumbnail_url '/other'" in d for d in got)
        assert any("serves image 20" in d for d in got)

    def test_two_heroes_or_an_excluded_hero_deviate(self) -> None:
        rows = self._rows()
        rows[0]["is_hero"] = True
        assert any("hero row(s)" in d for d in PL.deviations(self._expected(), self._sites(), rows))


# ================================================================================ the pictures
class _Images:
    def __init__(self, path: Path) -> None:
        self.path = path

    def path_for(self, site_id: str, filename: str) -> Path:
        return self.path


class TestThePictures:
    def _png(self, path: Path) -> Path:
        from PIL import Image

        Image.new("RGB", (40, 30), (120, 80, 40)).save(path, format="PNG")
        return path

    def test_a_gallery_file_is_shown_only_at_production_s_size(self, tmp_path: Path) -> None:
        path = self._png(tmp_path / "hero.webp")
        pictures = V.Pictures(_Images(path), FakeCommons())  # type: ignore[arg-type]
        good = row(1, THASOS, "Thasos.jpg", size=path.stat().st_size)
        assert pictures.gallery(THASOS, good)[:2] == b"\xff\xd8"  # a JPEG, as the gallery audit's
        with pytest.raises(ST.StateError, match="refresh the offsite copy"):
            pictures.gallery(THASOS, row(1, THASOS, "Thasos.jpg", size=path.stat().st_size + 1))

    def test_an_address_that_serves_a_page_is_unfetchable(self, tmp_path: Path) -> None:
        page = tmp_path / "page"
        page.write_bytes(b"<html>not a picture</html>")

        class _Download:
            def download(self, url: str) -> Path:
                return page

        pictures = V.Pictures(_Images(page), _Download())  # type: ignore[arg-type]
        with pytest.raises(C.Unfetchable, match="serves no image"):
            pictures.url("https://en.wikipedia.org/wiki/Q%27asa_Pata")


# ======================================================================== the no-image report
CLAIMED_SITE = "1f0d4b8f-5a11-4a6e-9a6a-0f0d4b8f5a11"
NO_ITEM_SITE = "2f0d4b8f-5a11-4a6e-9a6a-0f0d4b8f5a22"
EMPTY_CATEGORY_SITE = "3f0d4b8f-5a11-4a6e-9a6a-0f0d4b8f5a33"
#: A P373 category whose members are no still picture, next to one that is: the site claims a file,
#: the run exported a picture and named the sound it could not serve.
NO_PICTURE = [
    {
        "file": "Priene cooking.webm",
        "why": 'in the site\'s Commons category "Priene" (P373)',
        "status": V.NOT_A_PICTURE,
        "detail": "video/webm",
    }
]


class TestTheNoImageReport:
    """The goal's clause that no model gate can block: every curated site that serves no image,
    with the reason measured for that site - a row per site, not a number, not an open point."""

    def _run(self, tmp_path: Path, *, claiming: bool = False, empty_claim: bool = False) -> Path:
        """A read of four shown sites and one retired: Thasos serves a gallery row its item vouches
        for, Ahu Akivi serves nothing and its item claims nothing, a settlement serves nothing and
        has no item at all. With `claiming` a site that serves nothing while its item's category
        lists a file, with `empty_claim` one whose category lists none."""
        run = tmp_path / "served-image-2026-10-05"
        data = read_fixture()
        shown = [
            site(THASOS, "Archaeological Site of Ancient Thasos", None),
            site(NOTHING, "Ahu Akivi", None),
            site(NO_ITEM_SITE, "Settlement without an item", None),
        ]
        qids: dict[str, str | None] = {THASOS: "Q2", NOTHING: "Q3", NO_ITEM_SITE: None}
        entities = [entity("Q2", p18=["Thasos.jpg"]), entity("Q3")]
        if claiming:
            shown.append(site(CLAIMED_SITE, "Ruin of Priene", None))
            qids[CLAIMED_SITE] = "Q5"
            entities.append(entity("Q5", p373=["Priene"]))
        if empty_claim:
            shown.append(site(EMPTY_CATEGORY_SITE, "Quriwayrachina", None))
            qids[EMPTY_CATEGORY_SITE] = "Q6"
            entities.append(entity("Q6", p373=["Quriwayrachina, La Convecion"]))
        data["sites"] = shown
        data["images"] = [row(1, THASOS, "Thasos.jpg", hero=True, lead=True)]
        data["retired"] = [RETIRED_SITE]
        state = write_read(run, data)
        write_harvest(tmp_path / "harvest", qids, entities)
        PC.write_prechecks(
            run / PC.PRECHECK_FILE,
            PC.run_precheck(state, PC.load_harvest(tmp_path / "harvest"), FakeCommons()),
        )
        return run

    def _commons(self) -> FakeCommons:
        """Commons that lists one file in "Priene" and nothing in every other category - the
        measured state of the four sites whose P373 category names no file."""
        return FakeCommons(members={"Priene": ["Ruin.jpg"]})

    def _export(
        self,
        run: Path,
        *,
        claimed: list[str],
        asked: list[str],
        unavailable: dict[str, list[dict[str, Any]]] | None = None,
        precheck_sha256: str | None = None,
    ) -> None:
        ST.write_text_once(
            run / V.EXPORT_REPLACE,
            ST.json_text(
                {
                    "precheck_sha256": precheck_sha256 or ST.file_sha256(run / PC.PRECHECK_FILE),
                    "prompt_id": V.REPLACE_PROMPT_ID,
                    "questions_sha256": "0" * 64,
                    "claimed_sites": list(claimed),
                    "batches": {"replace-001": list(asked)} if asked else {},
                    "without_candidates": [],
                    "unavailable": unavailable or {},
                }
            ),
        )

    def _report(self, tmp_path: Path, run: Path) -> dict[str, dict[str, Any]]:
        NR.write_report(run, tmp_path / "harvest", self._commons())
        return {r["site_id"]: r for r in V.read_jsonl(run / NR.REPORT_FILE)}

    def test_a_site_that_serves_nothing_and_claims_nothing_is_reported_as_having_no_claim(
        self, tmp_path: Path
    ) -> None:
        run = self._run(tmp_path)
        got = self._report(tmp_path, run)[NOTHING]
        assert got["reason"] == NR.NO_CLAIM
        assert got["claim"] == {"p18": [], "p373": []}
        assert got["serves_image"] is False

    def test_a_site_that_serves_nothing_without_an_item_is_reported_as_such(
        self, tmp_path: Path
    ) -> None:
        run = self._run(tmp_path)
        got = self._report(tmp_path, run)[NO_ITEM_SITE]
        assert got["reason"] == NR.NO_ITEM
        assert got["qid"] is None

    def test_a_claiming_site_the_export_asks_about_is_reported_as_open(
        self, tmp_path: Path
    ) -> None:
        run = self._run(tmp_path, claiming=True)
        self._export(run, claimed=[CLAIMED_SITE], asked=[CLAIMED_SITE])
        got = self._report(tmp_path, run)[CLAIMED_SITE]
        assert got["reason"] == NR.CLAIMED_OPEN
        assert got["claim"] == {"p18": [], "p373": ["Priene"]}
        assert got["export"]["candidates"] == 1

    def test_a_claiming_site_whose_every_file_is_no_picture_is_reported_as_such(
        self, tmp_path: Path
    ) -> None:
        run = self._run(tmp_path, claiming=True)
        self._export(run, claimed=[CLAIMED_SITE], asked=[], unavailable={CLAIMED_SITE: NO_PICTURE})
        got = self._report(tmp_path, run)[CLAIMED_SITE]
        assert got["reason"] == NR.CLAIMED_NO_PICTURE
        assert got["export"] == {"candidates": 0, "unavailable": NO_PICTURE}

    def test_an_open_site_keeps_the_files_the_export_could_not_serve(self, tmp_path: Path) -> None:
        run = self._run(tmp_path, claiming=True)
        self._export(
            run,
            claimed=[CLAIMED_SITE],
            asked=[CLAIMED_SITE],
            unavailable={CLAIMED_SITE: NO_PICTURE},
        )
        got = self._report(tmp_path, run)[CLAIMED_SITE]
        assert got["reason"] == NR.CLAIMED_OPEN
        assert got["export"]["unavailable"] == NO_PICTURE

    def test_a_claiming_site_whose_category_names_no_file_is_reported_without_an_export(
        self, tmp_path: Path
    ) -> None:
        run = self._run(tmp_path, empty_claim=True)
        got = self._report(tmp_path, run)[EMPTY_CATEGORY_SITE]
        assert got["reason"] == NR.CLAIMED_NO_FILE
        assert got["export"] is None
        assert "Quriwayrachina, La Convecion" in got["detail"]

    def test_a_claim_with_no_file_named_does_not_ask_for_an_export(self, tmp_path: Path) -> None:
        run = self._run(tmp_path, empty_claim=True)
        summary = NR.write_report(run, tmp_path / "harvest", self._commons())
        assert summary["export_replace_sha256"] is None

    def test_the_retired_sites_are_reported_as_retired(self, tmp_path: Path) -> None:
        run = self._run(tmp_path)
        assert self._report(tmp_path, run)[RETIRED_SITE]["reason"] == NR.RETIRED

    def test_a_site_that_serves_an_image_is_not_in_the_report(self, tmp_path: Path) -> None:
        run = self._run(tmp_path)
        assert THASOS not in self._report(tmp_path, run)

    def test_the_counts_close_over_every_curated_site(self, tmp_path: Path) -> None:
        run = self._run(tmp_path, claiming=True, empty_claim=True)
        self._export(run, claimed=[CLAIMED_SITE], asked=[CLAIMED_SITE])
        summary = NR.write_report(run, tmp_path / "harvest", self._commons())
        counts = summary["counts"]
        assert counts["curated"] == counts["shown"] + counts["retired"]
        assert counts["shown"] == counts["confirmed"] + counts["unconfirmed"] + counts["no_image"]
        assert counts["no_image"] == sum(counts["reasons"][r] for r in NR.NO_IMAGE_REASONS)
        assert (counts["curated"], counts["shown"], counts["no_image"]) == (6, 5, 4)
        assert summary["addressable_remainder"] == 1

    def test_it_refuses_a_claiming_site_the_export_does_not_cover(self, tmp_path: Path) -> None:
        run = self._run(tmp_path, claiming=True)
        self._export(run, claimed=[], asked=[])
        with pytest.raises(ST.StateError, match=CLAIMED_SITE):
            NR.write_report(run, tmp_path / "harvest", self._commons())

    def test_it_refuses_a_precheck_the_export_was_not_run_on(self, tmp_path: Path) -> None:
        run = self._run(tmp_path, claiming=True)
        self._export(run, claimed=[CLAIMED_SITE], asked=[CLAIMED_SITE], precheck_sha256="0" * 64)
        with pytest.raises(ST.StateError, match="pre-check"):
            NR.write_report(run, tmp_path / "harvest", self._commons())

    def test_it_refuses_an_export_that_asks_about_a_site_serving_an_image(
        self, tmp_path: Path
    ) -> None:
        run = self._run(tmp_path, claiming=True)
        self._export(run, claimed=[CLAIMED_SITE], asked=[CLAIMED_SITE, THASOS])
        with pytest.raises(ST.StateError, match=THASOS):
            NR.write_report(run, tmp_path / "harvest", self._commons())

    def test_it_refuses_without_a_replace_export(self, tmp_path: Path) -> None:
        run = self._run(tmp_path, claiming=True)
        with pytest.raises(ST.StateError, match="export-replace"):
            NR.write_report(run, tmp_path / "harvest", self._commons())

    def test_it_refuses_a_site_the_read_holds_without_a_precheck_row(self, tmp_path: Path) -> None:
        run = self._run(tmp_path)
        path = run / PC.PRECHECK_FILE
        rows = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        path.unlink()
        path.write_text("\n".join(rows[1:]) + "\n", encoding="utf-8")
        with pytest.raises(ST.StateError, match="pre-check row"):
            NR.write_report(run, tmp_path / "harvest", self._commons())

    def test_the_report_is_written_once(self, tmp_path: Path) -> None:
        run = self._run(tmp_path, claiming=True)
        self._export(run, claimed=[CLAIMED_SITE], asked=[CLAIMED_SITE])
        NR.write_report(run, tmp_path / "harvest", self._commons())
        with pytest.raises(ST.StateError, match="never replaced"):
            NR.write_report(run, tmp_path / "harvest", self._commons())
