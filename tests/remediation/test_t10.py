"""Does T10 actually have teeth?

T10 spends the VLM budget: tier D is audited with zero calls, tiers A and B with one call per
image, tier C by sampling. These tests feed it synthetic snapshots and a hand-written signal
index whose truth is known by construction, and assert that each signal moves the tier in the
direction the plan describes - and, just as importantly, that a signal which *could not* be
computed keeps its row out of the zero-call tier. A check that files everything as "clear" and
a check that files everything as "suspect" are equally useless, and the second one cannot be
noticed from a green run.

They are deliberately not end-to-end: no snapshot, no network. The collector runs against a
Fetcher stand-in with canned answers, which is also how the API behaviours that decide
correctness are pinned down: a `maxlag` body is an HTTP 200 with an error inside (reading it
as "this site has no category" would invent a fact for 50 sites), a continuation response
carries only part of a batch, and a refused batch must be split rather than dropped.
"""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[2]
CENSUS_PARENT = REPO / "scripts" / "remediation"
if str(CENSUS_PARENT) not in sys.path:
    sys.path.insert(0, str(CENSUS_PARENT))

from census import model as M  # noqa: E402
from census.fetch import FetchError  # noqa: E402

EXPORTED_AT = "2026-09-20T20:20:01+02:00"
#: Pinned: the harness has to know the file name before the module fixture exists.
INDEX_NAME = "gallery_signals.json"


@pytest.fixture(scope="module")
def t10() -> Any:
    return importlib.import_module("census.tests.t10_gallery_tiers")


def test_the_index_file_name_is_the_one_the_module_writes(t10: Any) -> None:
    assert t10.INDEX_NAME == INDEX_NAME


# ------------------------------------------------------------------------------- fixtures
def _site(
    sid: str, name: str, *, qid: str | None = None, lat: float = 0.0, lon: float = 0.0
) -> dict[str, Any]:
    return {
        "id": sid,
        "source_id": "ancient_nerds",
        "name": name,
        "qid": qid,
        "lat": lat,
        "lon": lon,
    }


def _img(
    img_id: int,
    site_id: str,
    name: str,
    *,
    hero: bool = False,
    excluded: bool = False,
    title: str | None = None,
    commons: bool = True,
) -> dict[str, Any]:
    """One `wiki_images` row, in the shape the check reads."""
    if commons:
        original = f"https://upload.wikimedia.org/wikipedia/commons/4/4f/{name}"
        page: str | None = f"https://commons.wikimedia.org/wiki/File%3A{name}"
    else:
        original = f"/data/images/wiki/{site_id[:8]}/hero.webp"
        page = None
    return {
        "id": img_id,
        "site_id": site_id,
        "filename": name.replace("_", " "),
        "title": title if title is not None else name.rsplit(".", 1)[0].replace("_", " "),
        "original_url": original,
        "commons_page_url": page,
        "is_hero": hero,
        "is_excluded": excluded,
    }


def _index(
    p373: dict[str, dict[str, Any]] | None = None,
    files: dict[str, dict[str, Any]] | None = None,
    parents: dict[str, dict[str, Any]] | None = None,
    exported_at: str | None = None,
) -> dict[str, Any]:
    """The parts of the signal index a test wants to decide itself."""
    out: dict[str, Any] = {"p373": p373 or {}, "files": files or {}, "parents": parents or {}}
    if exported_at is not None:
        out["snapshot_exported_at"] = exported_at
    return out


DARA_P373 = {"s1": {"qid": "Q585145", "status": "ok", "category": "Dara"}}
ISHTAR_P373 = {"s2": {"qid": "Q207140", "status": "ok", "category": "Ishtar Gate"}}


class Harness:
    """The parts of Context T10 reads: sites, snapshot rows, the cache path, the network.

    The index it writes is built the way the collector builds it - file and parent names
    normalised, the site's own P373 category left raw - and every referenced file gets a
    record unless the test says otherwise, because `_read_index` insists on full coverage.
    """

    def __init__(
        self,
        t10: Any,
        tmp_path: Path,
        sites: list[dict[str, Any]],
        images: list[dict[str, Any]],
        index: dict[str, Any] | None = None,
        net: Any = None,
        autofill: bool = True,
    ) -> None:
        self.sites = [{k: v for k, v in site.items() if k != "qid"} for site in sites]
        by_site: dict[str, list[dict[str, Any]]] = {}
        for row in images:
            by_site.setdefault(str(row["site_id"]), []).append(row)
        ext = [
            {"site_id": site["id"], "kind": "wikidata_qid", "value": site["qid"]}
            for site in sites
            if site.get("qid")
        ]
        self.snap = SimpleNamespace(
            rows=lambda table: (
                images if table == "wiki_images" else ext if table == "site_external_ids" else []
            ),
            images=lambda sid: by_site.get(str(sid), []),
            exported_at=lambda: EXPORTED_AT,
            ids_of_kind=lambda kind: (
                {r["site_id"]: r["value"] for r in ext} if kind == "wikidata_qid" else {}
            ),
        )
        self.cache = tmp_path
        self._net = net
        if index is not None:
            (tmp_path / INDEX_NAME).write_text(
                json.dumps(self._payload(t10, index, images, autofill)), encoding="utf-8"
            )

    @staticmethod
    def _payload(
        t10: Any, index: dict[str, Any], images: list[dict[str, Any]], autofill: bool
    ) -> dict[str, Any]:
        files = {
            name: {
                "status": rec["status"],
                "categories": [t10.normalize_category(c) for c in rec.get("categories", [])],
                "raw_categories": rec.get(
                    "raw_categories", [f"Category:{c}" for c in rec.get("categories", [])]
                ),
            }
            for name, rec in index["files"].items()
        }
        parents = {
            cat: {
                "status": rec["status"],
                "parents": [t10.normalize_category(p) for p in rec.get("parents", [])],
                "titles": rec.get("titles", []),
            }
            for cat, rec in index["parents"].items()
        }
        if autofill:
            for row in images:
                name = t10.commons_file_name(row)
                if name:
                    files.setdefault(name, {"status": "ok", "categories": [], "raw_categories": []})
            for rec in files.values():
                for cat in rec["categories"]:
                    parents.setdefault(cat, {"status": "ok", "parents": [], "titles": []})
        return {
            "snapshot_exported_at": index.get("snapshot_exported_at", EXPORTED_AT),
            "p373": index["p373"],
            "files": files,
            "parents": parents,
        }

    def net(self) -> Any:
        assert self._net is not None, "this harness has no network"
        return self._net


def _tier_of(findings: list[M.Finding], image_id: int) -> str:
    hits = [f for f in findings if f.field == f"wiki_images:{image_id}"]
    assert len(hits) == 1, f"expected exactly one tier for image {image_id}, got {len(hits)}"
    return str(hits[0].current_value["tier"])


def _finding(findings: list[M.Finding], image_id: int) -> M.Finding:
    hits = [f for f in findings if f.field == f"wiki_images:{image_id}"]
    assert len(hits) == 1, f"expected exactly one tier for image {image_id}, got {len(hits)}"
    return hits[0]


DARA = _site("s1", "Dara Fortress", qid="Q585145", lat=37.28, lon=40.79)
#: ~1,050 km from Dara, and the plan's own example of a museum city.
ISHTAR = _site("s2", "Ishtar Gate", qid="Q207140", lat=32.54, lon=44.42)


# ------------------------------------------------------------------------- the tier ladder
class TestTierPrecedence:
    """Hero > suspect > clear > grey - each step's reason for being on top."""

    def test_a_hero_is_audited_even_when_it_is_clear(self, t10, tmp_path):
        """§6.3/§6.5: every hero gets a VLM call, so tier D must not swallow one."""
        images = [_img(1, "s1", "Dara_Fortress_hero.jpg", hero=True)]
        ctx = Harness(
            t10,
            tmp_path,
            [DARA],
            images,
            _index(
                p373=DARA_P373,
                files={"Dara_Fortress_hero.jpg": {"status": "ok", "categories": ["Dara"]}},
            ),
        )
        got = t10.run(ctx)
        assert _tier_of(got, 1) == "A"
        assert got[0].test_id == "T10/tier-A"
        assert got[0].current_value["reason"] == "hero"

    def test_a_hero_that_also_carries_core_stays_a_hero(self, t10, tmp_path):
        """One row, one tier: a hero that is also suspect must not produce two findings."""
        images = [_img(1, "s1", "plan_of_Dara.jpg", hero=True)]
        ctx = Harness(t10, tmp_path, [DARA], images, _index(p373=DARA_P373))
        got = t10.run(ctx)
        assert len(got) == 1, [f.test_id for f in got]
        assert _tier_of(got, 1) == "A"
        assert got[0].current_value["reason"] == "hero"
        assert got[0].current_value["signals"]["E"] is True, "the CORE signal is still recorded"

    def test_suspect_wins_over_clear(self, t10, tmp_path):
        """The plan's safe class only excludes *word* signals; S must still win, or a
        cross-site image would go into the zero-call tier."""
        images = [
            _img(1, "s1", "Dara_Fortress_from_air.jpg"),
            _img(2, "s2", "Dara_Fortress_from_air.jpg"),
        ]
        ctx = Harness(
            t10,
            tmp_path,
            [DARA, ISHTAR],
            images,
            _index(
                p373=DARA_P373 | ISHTAR_P373,
                files={"Dara_Fortress_from_air.jpg": {"status": "ok", "categories": ["Dara"]}},
            ),
        )
        got = t10.run(ctx)
        assert _tier_of(got, 1) == "B"
        assert _tier_of(got, 2) == "B", "the same file, differently named site: suspect, not clear"
        assert any("Dara Fortress" in (e.quote or "") for e in _finding(got, 2).evidence), (
            "the second site's evidence must name the first site"
        )

    def test_proven_in_category_membership_is_what_makes_clear(self, t10, tmp_path):
        images = [_img(1, "s1", "Dara_Fortress_walls.jpg")]
        ctx = Harness(
            t10,
            tmp_path,
            [DARA],
            images,
            _index(
                p373=DARA_P373,
                files={"Dara_Fortress_walls.jpg": {"status": "ok", "categories": ["Dara"]}},
            ),
        )
        got = t10.run(ctx)
        f = _finding(got, 1)
        assert f.current_value["tier"] == "D"
        assert f.current_value["reason"] == "in-category-clear"
        assert f.confidence is M.Confidence.AUTHORITATIVE
        assert f.proposal is M.Proposal.NONE
        assert "no VLM call" in f.note
        assert f.current_value["signals"]["P"] is False

    def test_the_downloaders_one_subcategory_level_counts_as_membership(self, t10, tmp_path):
        """The file sits in a subcategory of the site's category: the project's own
        downloader would have fetched it from there, so it is not "not in the category"."""
        images = [_img(1, "s1", "Dara_Fortress_arch.jpg")]
        ctx = Harness(
            t10,
            tmp_path,
            [DARA],
            images,
            _index(
                p373=DARA_P373,
                files={
                    "Dara_Fortress_arch.jpg": {"status": "ok", "categories": ["Dara (Fortress)"]}
                },
                parents={"dara fortress": {"status": "ok", "parents": ["Category:Dara"]}},
            ),
        )
        got = t10.run(ctx)
        assert _tier_of(got, 1) == "D"
        assert _finding(got, 1).current_value["signals"]["P"] is False


class TestNothingUnprovenBecomesClear:
    """The one error this census must not make: reading "could not check" as "clean"."""

    def test_a_site_without_a_p373_category_never_reaches_clear(self, t10, tmp_path):
        """The plan's 1,448 sites with a missing or wrong anchor: D must be unreachable."""
        images = [_img(1, "s1", "Dara_Fortress_walls.jpg")]
        ctx = Harness(
            t10,
            tmp_path,
            [DARA],
            images,
            _index(
                p373={"s1": {"qid": "Q585145", "status": "absent", "category": None}},
                files={"Dara_Fortress_walls.jpg": {"status": "ok", "categories": ["Dara"]}},
            ),
        )
        got = t10.run(ctx)
        f = _finding(got, 1)
        assert f.current_value["tier"] == "C"
        assert f.current_value["reason"] == "p-unproven"
        assert f.current_value["signals"]["P"] is None
        assert f.confidence is M.Confidence.UNVERIFIABLE

    def test_a_site_without_a_qid_anchor_never_reaches_clear(self, t10, tmp_path):
        """386 sites have no QID at all - there is nothing to look a category up with."""
        site = _site("s9", "Dara Fortress", qid=None, lat=37.28, lon=40.79)
        ctx = Harness(t10, tmp_path, [site], [_img(1, "s9", "Dara_Fortress_walls.jpg")], _index())
        got = t10.run(ctx)
        assert _tier_of(got, 1) == "C"
        assert _finding(got, 1).current_value["reason"] == "p-unproven"

    def test_a_file_whose_category_list_is_unknown_never_reaches_clear(self, t10, tmp_path):
        """Commons answered for other files but not this one: still "we do not know"."""
        images = [_img(1, "s1", "Dara_Fortress_walls.jpg")]
        ctx = Harness(
            t10,
            tmp_path,
            [DARA],
            images,
            _index(
                p373=DARA_P373,
                files={"Dara_Fortress_walls.jpg": {"status": "unresolved"}},
            ),
        )
        got = t10.run(ctx)
        assert _tier_of(got, 1) == "C"
        assert _finding(got, 1).current_value["reason"] == "p-unproven"

    def test_a_row_without_commons_identity_never_reaches_clear(self, t10, tmp_path):
        images = [_img(1, "s1", "hero.webp", commons=False, title="Dara Fortress")]
        ctx = Harness(t10, tmp_path, [DARA], images, _index(p373=DARA_P373))
        got = t10.run(ctx)
        f = _finding(got, 1)
        assert f.current_value["tier"] == "C"
        assert f.current_value["signals"]["S"] is None, "no Commons file, no cross-site answer"
        assert f.current_value["signals"]["P"] is None

    def test_a_file_outside_the_category_is_grey_not_clear(self, t10, tmp_path):
        images = [_img(1, "s1", "Dara_Fortress_walls.jpg")]
        ctx = Harness(
            t10,
            tmp_path,
            [DARA],
            images,
            _index(
                p373=DARA_P373,
                files={"Dara_Fortress_walls.jpg": {"status": "ok", "categories": ["Castles"]}},
            ),
        )
        got = t10.run(ctx)
        f = _finding(got, 1)
        assert f.current_value["tier"] == "C"
        assert f.current_value["reason"] == "not-in-category"
        assert f.current_value["signals"]["P"] is True

    def test_the_own_name_must_be_in_the_filename_not_only_the_title(self, t10, tmp_path):
        """§6.5's safe class asks for the name in the *filename*."""
        images = [_img(1, "s1", "IMG_2031.jpg", title="Dara Fortress, walls")]
        ctx = Harness(
            t10,
            tmp_path,
            [DARA],
            images,
            _index(
                p373=DARA_P373,
                files={"IMG_2031.jpg": {"status": "ok", "categories": ["Dara"]}},
            ),
        )
        got = t10.run(ctx)
        f = _finding(got, 1)
        assert f.current_value["tier"] == "C"
        assert f.current_value["reason"] == "name-not-in-filename"
        assert f.current_value["signals"]["F"] is False, "the name *is* elsewhere in the row"


# ------------------------------------------------------------------------------- signals
class TestSignals:
    def _first(self, t10, tmp_path, images, *, index=None, sites=None):
        ctx = Harness(
            t10,
            tmp_path,
            sites or [DARA],
            images,
            index if index is not None else _index(p373=DARA_P373),
        )
        return t10.run(ctx)[0]

    def test_the_six_printed_non_photo_terms_fire_and_nothing_else(self, t10):
        assert t10.matched_terms(["map"], t10.NON_PHOTO_TERMS_NORM) == ["map"]
        assert t10.matched_terms(["plans"], t10.NON_PHOTO_TERMS_NORM) == ["plans"]
        assert t10.matched_terms(["planting"], t10.NON_PHOTO_TERMS_NORM) == []
        assert t10.matched_terms(["mapping"], t10.NON_PHOTO_TERMS_NORM) == []
        assert len(t10.NON_PHOTO_TERMS) == 6, "six of the plan's 67 terms - not more"

    def test_signal_b_is_recorded_as_unavailable(self, t10, tmp_path):
        f = self._first(
            t10, tmp_path, [_img(1, "s1", "Dara_Fortress.jpg")], index=_index(p373=DARA_P373)
        )
        assert f.current_value["signals"]["B"] is None
        assert "not in this repository" in t10.B_MUSEUM_CITY

    def test_a_non_photo_word_in_the_filename_is_a_core_signal(self, t10, tmp_path):
        f = self._first(
            t10, tmp_path, [_img(1, "s1", "engraving_of_Dara.jpg")], index=_index(p373=DARA_P373)
        )
        assert f.current_value["tier"] == "B"
        assert f.current_value["signals"]["E"] is True
        assert any("engraving" in (e.quote or "") for e in f.evidence)

    def test_a_museum_word_in_a_commons_category_is_a_core_signal(self, t10, tmp_path):
        """A's channel includes the Commons category - which the P fetch delivers anyway."""
        f = self._first(
            t10,
            tmp_path,
            [_img(1, "s1", "Walls.jpg")],
            index=_index(
                p373=DARA_P373,
                files={"Walls.jpg": {"status": "ok", "categories": ["Museums in Iraq"]}},
            ),
        )
        assert f.current_value["tier"] == "B"
        assert f.current_value["signals"]["A"] is True

    def test_the_dictionary_matches_whole_tokens(self, t10):
        assert t10.name_in_text("dara", t10.normalize_text("Dara Fortress")) is True
        assert t10.name_in_text("dara", t10.normalize_text("Darax Fortress")) is False

    def test_a_place_token_of_a_distant_site_is_a_core_signal(self, t10, tmp_path):
        f = self._first(
            t10,
            tmp_path,
            [_img(1, "s1", "Ishtar_Gate_relief.jpg", title="Ishtar Gate relief")],
            index=_index(p373=DARA_P373 | ISHTAR_P373),
            sites=[DARA, ISHTAR],
        )
        assert f.current_value["signals"]["D"] is True
        assert f.current_value["tier"] == "B"
        assert any("Ishtar Gate" in (e.quote or "") for e in f.evidence)

    def test_a_place_token_of_a_nearby_site_is_not(self, t10, tmp_path):
        """Two curated sites share the token "dara" 13 km apart - no D hit either way."""
        near = _site("s4", "Dara Fortress North", qid=None, lat=37.40, lon=40.79)
        images = [_img(1, "s1", "Dara_Fortress_North_walls.jpg")]
        ctx = Harness(t10, tmp_path, [DARA, near], images, _index(p373=DARA_P373))
        got = t10.run(ctx)
        assert got[0].current_value["signals"]["D"] is False, got[0].current_value

    def test_s_compares_normalised_names_not_raw_ones(self, t10, tmp_path):
        """Two sites whose names differ only by diacritics are not "differently named"."""
        plain = _site("s5", "Merida", qid=None, lat=38.91, lon=-6.34)
        accented = _site("s6", "Mérida", qid=None, lat=38.91, lon=-6.34)
        images = [
            _img(1, "s5", "Merida_amphitheatre.jpg"),
            _img(2, "s6", "Merida_amphitheatre.jpg"),
        ]
        ctx = Harness(t10, tmp_path, [plain, accented], images, _index())
        got = t10.run(ctx)
        assert [f.current_value["signals"]["S"] for f in got] == [False, False], got

    def test_different_names_on_one_file_are_s(self, t10, tmp_path):
        images = [_img(1, "s1", "Pergamon_altar.jpg"), _img(2, "s2", "Pergamon_altar.jpg")]
        ctx = Harness(t10, tmp_path, [DARA, ISHTAR], images, _index(p373=DARA_P373 | ISHTAR_P373))
        got = t10.run(ctx)
        assert [f.current_value["signals"]["S"] for f in got] == [True, True], got

    def test_haversine_is_in_kilometres(self, t10):
        assert t10.haversine_km(37.28, 40.79, 37.28, 40.79) == 0.0
        dara_to_ishtar = t10.haversine_km(37.28, 40.79, 32.54, 44.42)
        assert 600 < dara_to_ishtar < 1200, dara_to_ishtar

    def test_a_generic_token_that_only_looks_like_a_place_is_dropped(self, t10, tmp_path):
        """18,670 of 49,691 rows fired before this cut, on "temple", "from", "site" - the
        distance rule cannot tell a place name from a word a site name happens to contain."""
        sites = [DARA, ISHTAR, _site("s7", "Temple of Bel", qid=None, lat=34.55, lon=38.27)]
        images = [_img(i, "s1", f"temple_wall_{i}.jpg") for i in range(1, 5)]
        images.append(_img(9, "s1", "Ishtar_Gate_lion.jpg", title="Ishtar Gate lion"))
        ctx = Harness(t10, tmp_path, sites, images, _index(p373=DARA_P373 | ISHTAR_P373))
        sc = t10.build_site_context(ctx.sites)
        assert t10.distinctive_place_tokens(sc, ctx.snap.rows("wiki_images"), budget=4) == [
            "temple"
        ]
        index = t10._read_index(ctx)
        shares = t10.cross_site_shares(ctx, sc)
        fired = {
            img["id"]: t10.signals_for(img, "s1", sc, index, shares).other_place_token
            for img in images
        }
        assert set(fired.values()) == {False, True}, fired
        assert fired[9] is True, "the distinctive token still fires"

    def test_the_place_dictionary_keeps_the_most_distinctive_tokens(self, t10, tmp_path):
        sites = [_site("s1", "Ishtar Gate", qid=None), _site("s2", "Temple of Ishtar", qid=None)]
        rows = [_img(1, "s1", f"temple_{i}.jpg") for i in range(1, 5)]
        ctx = Harness(t10, tmp_path, sites, rows, _index())
        sc = t10.build_site_context(ctx.sites)
        t10.distinctive_place_tokens(sc, ctx.snap.rows("wiki_images"), budget=1)
        assert set(sc.place_tokens) == {"gate"} or set(sc.place_tokens) == {"temple"}, list(
            sc.place_tokens
        )

    def test_the_place_dictionary_is_derived_from_the_curated_names(self, t10):
        sc = t10.build_site_context(
            [
                {"id": "s1", "name": "Dara Fortress", "lat": 37.28, "lon": 40.79},
                {"id": "s2", "name": "El Dara", "lat": 37.30, "lon": 40.80},
            ]
        )
        assert "dara" in sc.place_tokens
        assert "el" not in sc.place_tokens, "two-letter articles identify nothing"
        assert sc.nearest_place("dara", "s1") == ("s1", 0.0)


# ---------------------------------------------------------------------------- the container
class TestRowsAndCoverage:
    def test_every_image_row_gets_exactly_one_tier(self, t10, tmp_path):
        images = [
            _img(1, "s1", "Dara_Fortress_hero.jpg", hero=True),
            _img(2, "s1", "Dara_Fortress_walls.jpg"),
            _img(3, "s1", "plan_of_Dara.jpg"),
            _img(4, "s1", "hero.webp", commons=False),
        ]
        ctx = Harness(
            t10,
            tmp_path,
            [DARA],
            images,
            _index(
                p373=DARA_P373,
                files={
                    "Dara_Fortress_hero.jpg": {"status": "ok", "categories": ["Dara"]},
                    "Dara_Fortress_walls.jpg": {"status": "ok", "categories": ["Dara"]},
                    "plan_of_Dara.jpg": {"status": "ok", "categories": ["Dara"]},
                },
            ),
        )
        got = t10.run(ctx)
        assert len(got) == len(images)
        assert {f.field for f in got} == {f"wiki_images:{i}" for i in (1, 2, 3, 4)}
        assert {f.current_value["tier"] for f in got} == {"A", "B", "C", "D"}, [
            f.current_value["tier"] for f in got
        ]

    def test_an_excluded_row_is_triaged_like_any_other(self, t10, tmp_path):
        """The tier is about the row; whether the row is servable is the export's decision."""
        ctx = Harness(
            t10,
            tmp_path,
            [DARA],
            [_img(1, "s1", "plan.jpg", excluded=True)],
            _index(p373=DARA_P373),
        )
        got = t10.run(ctx)
        assert len(got) == 1
        assert got[0].current_value["is_excluded"] is True
        assert got[0].current_value["tier"] == "B"

    def test_nothing_here_is_auto_applicable(self, t10, tmp_path):
        images = [_img(1, "s1", "plan.jpg"), _img(2, "s1", "Dara_Fortress.jpg", hero=True)]
        ctx = Harness(t10, tmp_path, [DARA], images, _index(p373=DARA_P373))
        got = t10.run(ctx)
        assert got, "the fixture must produce findings"
        for f in got:
            assert f.proposal is M.Proposal.NONE
            assert not f.applicable, "a tier is a work order, not a database write"
            assert f.evidence, f"{f.test_id} without evidence"

    def test_applies_only_to_sites_with_images(self, t10, tmp_path):
        ctx = Harness(
            t10,
            tmp_path,
            [DARA, ISHTAR],
            [_img(1, "s1", "walls.jpg")],
            _index(p373=DARA_P373 | ISHTAR_P373),
        )
        assert t10.applies_to({"id": "s1"}, ctx) is True
        assert t10.applies_to({"id": "s2"}, ctx) is False


class TestIndexContract:
    def test_run_refuses_a_missing_index(self, t10, tmp_path):
        ctx = Harness(t10, tmp_path, [DARA], [_img(1, "s1", "walls.jpg")], index=None)
        with pytest.raises(FileNotFoundError, match="collect"):
            t10.run(ctx)

    def test_run_refuses_an_index_from_another_snapshot(self, t10, tmp_path):
        """Collecting truth about snapshot A and applying it to snapshot B is a silent lie."""
        index = _index(p373=DARA_P373, exported_at="2026-01-01T00:00:00+01:00")
        ctx = Harness(t10, tmp_path, [DARA], [_img(1, "s1", "walls.jpg")], index)
        with pytest.raises(RuntimeError, match="re-collect"):
            t10.run(ctx)

    def test_run_refuses_an_index_without_a_qid_site(self, t10, tmp_path):
        """A QID anchor the collector never asked about must not read as "no category"."""
        ctx = Harness(t10, tmp_path, [DARA], [_img(1, "s1", "walls.jpg")], _index(p373={}))
        with pytest.raises(RuntimeError, match="QID anchor"):
            t10.run(ctx)

    def test_run_refuses_an_index_that_does_not_cover_the_files(self, t10, tmp_path):
        index = _index(
            p373=DARA_P373, files={"some_other_file.jpg": {"status": "ok", "categories": []}}
        )
        ctx = Harness(t10, tmp_path, [DARA], [_img(1, "s1", "walls.jpg")], index, autofill=False)
        with pytest.raises(RuntimeError, match="does not match this snapshot"):
            t10.run(ctx)

    def test_run_refuses_a_missing_parent_record(self, t10, tmp_path):
        """Without it the one-subcategory-level hop would silently miss."""
        index = _index(
            p373=DARA_P373,
            files={"walls.jpg": {"status": "ok", "categories": ["Dara"]}},
            parents={},
        )
        ctx = Harness(t10, tmp_path, [DARA], [_img(1, "s1", "walls.jpg")], index, autofill=False)
        with pytest.raises(RuntimeError, match="one-subcategory-level"):
            t10.run(ctx)


# ------------------------------------------------------------------------------- the fetch
class FakeNet:
    """A Fetcher stand-in: canned bodies, order-preserving `map`, and a call log to count on."""

    def __init__(self, responder: Any):
        self.responder = responder
        self.calls: list[dict[str, Any]] = []

    def get_json(
        self, url: str, params: Any = None, ns: str = "json", force: bool = False
    ) -> dict[str, Any]:
        params = dict(params or {})
        self.calls.append({"url": url, "params": params, "force": force})
        body = self.responder(url, params, force)
        if isinstance(body, BaseException):
            raise body
        return {"json": body, "status": 200, "url": url}

    def map(self, fn: Any, items: Any, workers: int | None = None, desc: str = "") -> list[Any]:
        out = []
        for item in items:
            try:
                out.append(fn(item))
            except Exception as exc:  # recorded, never swallowed - as the real Fetcher does
                out.append(exc)
        return out


def _cat_page(titles: list[str], cats: dict[str, list[str]]) -> dict[str, Any]:
    pages = []
    for title in titles:
        entry: dict[str, Any] = {"ns": 6, "title": title}
        if title in cats:
            entry["categories"] = [{"ns": 14, "title": c} for c in cats[title]]
        else:
            entry["missing"] = True
        pages.append(entry)
    return {"batchcomplete": True, "query": {"pages": pages}}


class TestCollector:
    def test_the_p373_sweep_records_ok_absent_and_missing(self, t10, tmp_path):
        """A snak without a value is not a category, a missing entity is not "no category",
        and an entity without a P373 claim is a third fact again."""
        sites = [_site("s1", "A", qid="Q1"), _site("s2", "B", qid="Q2"), _site("s3", "C", qid="Q3")]
        net = FakeNet(
            lambda url, params, force: {
                "entities": {
                    "Q1": {"type": "item", "id": "Q1", "claims": {"P373": [{"mainsnak": {}}]}},
                    "Q2": {"type": "item", "id": "Q2", "claims": {"P88": []}},
                    "Q3": {"type": "item", "id": "Q3", "missing": ""},
                }
            }
        )
        ctx = Harness(t10, tmp_path, sites, [], None, net=net)
        entries = t10._sweep_p373(ctx)
        assert entries["s1"]["status"] == "absent"
        assert entries["s2"]["status"] == "absent"
        assert entries["s3"]["status"] == "missing"
        assert (tmp_path / t10.PART_P373).exists()

    def test_the_p373_sweep_keeps_a_real_category(self, t10, tmp_path):
        sites = [_site("s1", "Dara Fortress", qid="Q585145")]
        net = FakeNet(
            lambda url, params, force: {
                "entities": {
                    "Q585145": {
                        "type": "item",
                        "id": "Q585145",
                        "claims": {
                            "P373": [
                                {
                                    "mainsnak": {
                                        "snaktype": "value",
                                        "datavalue": {"value": "Dara", "type": "string"},
                                    }
                                }
                            ]
                        },
                    }
                }
            }
        )
        ctx = Harness(t10, tmp_path, sites, [], None, net=net)
        assert t10._sweep_p373(ctx)["s1"]["category"] == "Dara"

    def test_a_maxlag_answer_is_not_stored_as_an_absent_category(self, t10, tmp_path):
        """Wikimedia answers maxlag with HTTP 200, and the Fetcher caches bodies: a naive
        read would record "no category" for up to 50 sites at once."""
        sites = [_site("s1", "Dara Fortress", qid="Q585145")]
        answers = [
            {"error": {"code": "maxlag", "info": "Waiting for wdqs1018: 148 seconds lagged."}},
            {
                "entities": {
                    "Q585145": {
                        "type": "item",
                        "id": "Q585145",
                        "claims": {
                            "P373": [
                                {
                                    "mainsnak": {
                                        "snaktype": "value",
                                        "datavalue": {"value": "Dara", "type": "string"},
                                    }
                                }
                            ]
                        },
                    }
                }
            },
        ]
        net = FakeNet(lambda url, params, force: answers.pop(0) if answers else {"entities": {}})
        ctx = Harness(t10, tmp_path, sites, [], None, net=net)
        assert t10._sweep_p373(ctx)["s1"]["category"] == "Dara"
        assert net.calls[1]["force"] is True, "the cached maxlag body must be bypassed"
        assert "maxlag" not in net.calls[1]["params"], "the throttle is dropped, not ignored"
        part = json.loads((tmp_path / t10.PART_P373).read_text(encoding="utf-8"))
        assert part["maxlag"] == 1, "and the artefact says how often that was necessary"

    def test_a_batch_that_never_succeeds_raises_and_writes_no_part(self, t10, tmp_path):
        sites = [_site("s1", "Dara Fortress", qid="Q585145")]
        net = FakeNet(lambda url, params, force: FetchError("HTTP 500 from wikidata"))
        ctx = Harness(t10, tmp_path, sites, [], None, net=net)
        with pytest.raises(RuntimeError, match="resume from the cache"):
            t10._sweep_p373(ctx, backoff=0.0)
        assert not (tmp_path / t10.PART_P373).exists(), "a partial sweep must not look complete"

    def test_the_file_sweep_merges_continuations(self, t10, tmp_path):
        """A continuation response carries only the pages it advances: merging is the
        difference between a complete category list and a truncated one."""

        def responder(url: str, params: dict[str, Any], force: bool) -> dict[str, Any]:
            if "clcontinue" not in params:
                return {
                    "continue": {"clcontinue": "next"},
                    "query": {
                        "pages": [
                            {
                                "ns": 6,
                                "title": "File:Dara.jpg",
                                "categories": [{"ns": 14, "title": "Category:Ishtar Gate"}],
                            }
                        ]
                    },
                }
            return _cat_page(
                ["File:Dara.jpg"],
                {"File:Dara.jpg": ["Category:Dara", "Category:Fortresses"]},
            )

        ctx = Harness(
            t10, tmp_path, [DARA], [_img(1, "s1", "Dara.jpg")], None, net=FakeNet(responder)
        )
        entries = t10._sweep_files(ctx)
        assert entries["Dara.jpg"]["status"] == "ok"
        assert entries["Dara.jpg"]["categories"] == ["dara", "fortresses", "ishtar gate"]
        assert entries["Dara.jpg"]["raw_categories"] == [
            "Category:Dara",
            "Category:Fortresses",
            "Category:Ishtar Gate",
        ], "the titles the parent sweep has to ask"

    def test_the_file_sweep_reuses_its_part_file(self, t10, tmp_path):
        """A sweep that finished must not be repeated: that is what makes the run resumable."""
        net = FakeNet(
            lambda url, params, force: _cat_page(["File:Dara.jpg"], {"File:Dara.jpg": []})
        )
        ctx = Harness(t10, tmp_path, [DARA], [_img(1, "s1", "Dara.jpg")], None, net=net)
        first = t10._sweep_files(ctx)
        calls = len(net.calls)
        assert t10._sweep_files(ctx) == first
        assert len(net.calls) == calls, "the second sweep must not touch the network"

    def test_a_missing_file_and_an_unanswered_title_stay_apart(self, t10, tmp_path):
        rows = [_img(1, "s1", "gone.jpg"), _img(2, "s1", "unanswered.jpg")]
        net = FakeNet(lambda url, params, force: _cat_page(["File:gone.jpg"], {}))
        ctx = Harness(t10, tmp_path, [DARA], rows, None, net=net)
        entries = t10._sweep_files(ctx)
        assert entries["gone.jpg"]["status"] == "missing"
        assert entries["unanswered.jpg"]["status"] == "unresolved"

    def test_a_batch_the_api_refuses_is_split_not_dropped(self, t10, tmp_path):
        titles = [f"File:Name{i}.jpg" for i in range(4)]

        def responder(url: str, params: dict[str, Any], force: bool) -> Any:
            asked = params["titles"].split("|")
            if len(asked) > 1:
                return FetchError("HTTP 414 from commons")
            return _cat_page(asked, {asked[0]: []})

        ctx = Harness(t10, tmp_path, [DARA], [], None, net=FakeNet(responder))
        got = t10._entries_for_titles(ctx, titles, "t10_commons", [])
        assert sorted(got) == titles
        assert all(rec["status"] == "ok" for rec in got.values())

    def test_the_parent_sweep_asks_the_raw_category_title(self, t10, tmp_path):
        """The normalised name is for comparing, not for asking: "dara fortress" does not
        exist where "Dara (Fortress)" does (measured: 26/26 raw vs 5/26 normalised)."""
        asked: list[str] = []

        def responder(url: str, params: dict[str, Any], force: bool) -> dict[str, Any]:
            asked.append(params["titles"])
            return _cat_page(
                ["Category:Dara (Fortress)"], {"Category:Dara (Fortress)": ["Category:Dara"]}
            )

        ctx = Harness(t10, tmp_path, [DARA], [], None, net=FakeNet(responder))
        entries = t10._sweep_parents(
            ctx,
            {
                "Dara.jpg": {
                    "status": "ok",
                    "categories": ["dara fortress"],
                    "raw_categories": ["Category:Dara (Fortress)"],
                }
            },
        )
        assert asked == ["Category:Dara (Fortress)"]
        assert entries["dara fortress"]["parents"] == ["dara"]
        assert entries["dara fortress"]["status"] == "ok"

    def test_the_parent_sweep_merges_the_titles_of_one_normalised_name(self, t10, tmp_path):
        """Two raw titles can normalise to the same name; both are asked, parents merged."""
        answers = {
            "Category:Dara (Fortress)": ["Category:Dara"],
            "Category:Dara-Fortress": ["Category:Fortresses in Iraq"],
        }

        def responder(url: str, params: dict[str, Any], force: bool) -> dict[str, Any]:
            return _cat_page(params["titles"].split("|"), answers)

        ctx = Harness(t10, tmp_path, [DARA], [], None, net=FakeNet(responder))
        entries = t10._sweep_parents(
            ctx,
            {
                "Dara.jpg": {
                    "status": "ok",
                    "categories": ["dara fortress"],
                    "raw_categories": ["Category:Dara (Fortress)", "Category:Dara-Fortress"],
                }
            },
        )
        assert entries["dara fortress"]["parents"] == ["dara", "fortresses in iraq"]

    def test_a_part_file_from_the_old_schema_is_not_reused(self, t10, tmp_path):
        """Schema 1 asked the normalised titles and found parents for 14 % of categories."""
        (tmp_path / t10.PART_PARENTS).write_text(
            json.dumps(
                {
                    "entries": {},
                    "snapshot_exported_at": EXPORTED_AT,
                }
            ),
            encoding="utf-8",
        )
        net = FakeNet(
            lambda url, params, force: _cat_page(
                ["Category:Dara"], {"Category:Dara": ["Category:Ancient cities"]}
            )
        )
        ctx = Harness(t10, tmp_path, [DARA], [], None, net=net)
        entries = t10._sweep_parents(
            ctx,
            {
                "Dara.jpg": {
                    "status": "ok",
                    "categories": ["dara"],
                    "raw_categories": ["Category:Dara"],
                }
            },
        )
        assert net.calls, "a schema 1 part file must not spare the sweep"
        assert entries["dara"]["parents"] == ["ancient cities"]

    def test_collect_folds_the_three_sweeps_into_one_index(self, t10, tmp_path):
        def responder(url: str, params: dict[str, Any], force: bool) -> dict[str, Any]:
            if params["action"] == "wbgetentities":
                return {
                    "entities": {
                        "Q585145": {
                            "type": "item",
                            "id": "Q585145",
                            "claims": {
                                "P373": [
                                    {
                                        "mainsnak": {
                                            "snaktype": "value",
                                            "datavalue": {"value": "Dara", "type": "string"},
                                        }
                                    }
                                ]
                            },
                        }
                    }
                }
            return _cat_page(params["titles"].split("|"), {})

        ctx = Harness(
            t10, tmp_path, [DARA], [_img(1, "s1", "Dara.jpg")], None, net=FakeNet(responder)
        )
        # _cat_page answers "missing" for unknown titles, so the file gets no categories:
        # that is the honest outcome here, and it must not stop the index from being written.
        t10.collect(ctx)
        payload = json.loads((tmp_path / INDEX_NAME).read_text(encoding="utf-8"))
        assert payload["snapshot_exported_at"] == EXPORTED_AT
        assert payload["p373"]["s1"]["category"] == "Dara"
        assert payload["files"]["Dara.jpg"]["status"] == "missing"
        assert t10.run(ctx) != [], "and a run against that index still produces tiers"
