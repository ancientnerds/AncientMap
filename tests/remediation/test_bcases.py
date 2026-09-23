"""The owner cases of HUMAN_ONLY section B, decided from data (`scripts/remediation/bcases/`).

Every class is pinned by a case taken from the real examples the remaining-work map names - Q309
"history" on Clare, Suffolk; Calakmul stored 907 km off; Petroglyph Beach, whose Wikidata and Wikipedia
points are one point; Castro of Santa Trega and Khao Sam Kaeo, whose articles hold their items' points
cut to four decimals; the Pergamon Altar and a museum object stored at its museum; Dooey's Cairn and
Ballymacaldrack, one tomb recorded twice; Banias and Caesarea Philippi, one site on two sides of the
Golan line. Each guard has a test that goes red without it, and the mutation sweep
(`scripts/remediation/phase3/mutation_sweep.py`, "bcases") removes them one by one.

Nothing here reads the network or production: the fetcher and the psql reader are fakes that refuse
what the real ones refuse. The versioned deliverables (`output/remediation/bcases/`) are checked for
their shape and their pinned counts; the full re-classification needs the gitignored caches and skips
with its reason without them.
"""

from __future__ import annotations

import gzip
import json
import re
import sys
from collections import Counter
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest
import shapely
from shapely.geometry import box

REPO = Path(__file__).resolve().parents[2]
for _path in (REPO, REPO / "scripts" / "remediation"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from bcases import classify as C  # noqa: E402
from bcases import collect as K  # noqa: E402
from bcases import coord_plan as P  # noqa: E402
from bcases import inputs  # noqa: E402
from bcases import qid_research as R  # noqa: E402

OUT = REPO / "output" / "remediation" / "bcases"
DATA = REPO / "output" / "remediation"

SITE = "11111111-1111-4111-8111-111111111111"
OTHER = "22222222-2222-4222-8222-222222222222"
THIRD = "33333333-3333-4333-8333-333333333333"

# Calakmul, as production and Wikidata/Wikipedia held it on 2026-09-23.
CALAKMUL_STORED = (19.243221692240958, -98.34002245550043)
CALAKMUL_WD = (18.105, -89.81055555555555)
CALAKMUL_EN = (18.10539167, -89.81082778)
# Petroglyph Beach: both public points are downtown Juneau (plan anti-pattern 9).
JUNEAU = (58.301061, -134.413121)
WRANGELL = (56.4839, -132.3887)


# ── names and words ─────────────────────────────────────────────────────────────────────────────


def test_generic_words_and_elisions_do_not_make_two_names() -> None:
    names = {"Olympia": ["label:en"]}
    assert C.name_identity("Archaeological Site of Olympia", names) == ("N2", "Olympia")
    assert C.name_identity("Er-Grah Tumulus", {"tumulus d'Er Grah": ["label:fr"]})[0] == "N2"
    assert C.name_identity("Temple of Hibis", {"Hibis": ["label:en"]}) == ("N3", "Hibis")
    assert C.name_identity("Clare, Suffolk", {"history": ["label:en"]}) == ("none", None)


def test_a_modern_place_contains_a_site_and_an_ancient_one_is_the_site() -> None:
    for label in ("village", "human settlement", "comune of Italy", "municipal unit of Greece"):
        assert C.is_container_class(label), label
    for label in ("ancient city", "hillfort", "city walls", "Roman city", "submerged settlement"):
        assert not C.is_container_class(label), label
    # whole words only: a townhouse (a Chester row's class) is a building, not a town
    for label in ("townhouse", "hillside cave"):
        assert not C.is_container_class(label), label
    assert C.is_linear_or_areal_class("Roman road")
    assert not C.is_linear_or_areal_class("archaeological site")


def _name_finding(qid: str, name: str, test: str = "T01/name") -> dict[str, Any]:
    return {
        "site_id": SITE,
        "test_id": test,
        "current_value": name,
        "evidence": [{"url": f"https://www.wikidata.org/wiki/{qid}"}],
    }


def _site(name: str, qid: str | None, point: tuple[float, float] = (51.0, 0.0), **extra: Any):
    return {
        "id": SITE,
        "name": name,
        "lat": point[0],
        "lon": point[1],
        "lat_text": repr(point[0]),
        "lon_text": repr(point[1]),
        "geom_text": "0101000020E6100000",
        "qid": qid,
        "enwiki": None,
        "country": "England",
        **extra,
    }


def _name(qid: str, name: str, *, t01: Mapping[str, Any], names: Mapping[str, Any], **kw: Any):
    return C.classify_name(
        _name_finding(qid, name),
        _site(name, qid),
        census_enwiki=kw.pop("enwiki", None),
        names=names,
        t01=t01,
        labels=kw.pop("labels", {}),
        shared=kw.pop("shared", {}),
    )


def test_q309_history_is_a_wrong_link_not_a_name_to_keep() -> None:
    row = _name(
        "Q309",
        "Clare, Suffolk",
        t01={"Q309": {"en_label": "history", "lat": None, "lon": None}},
        names={"Q309": {"labels": {"en": "history"}}},
        enwiki="History",
    )
    assert (row["class"], row["group"]) == ("Q1", "wrong-link")
    assert any("has no P625" in e["quote"] for e in row["evidence"])


def test_a_stored_name_that_is_an_alias_is_kept_with_the_alias_as_evidence() -> None:
    row = _name(
        "Q1",
        "Hattusas",
        t01={"Q1": {"en_label": "Hattusa", "lat": 51.0, "lon": 0.0}},
        names={"Q1": {"labels": {"en": "Hattusa"}, "aliases": {"en": ["Hattusas"]}}},
    )
    assert (row["class"], row["group"], row["match"]) == ("N1", "keep", "Hattusas")
    assert any("alias:en" in e["quote"] for e in row["evidence"])


def test_a_transliteration_is_kept_and_a_far_item_is_a_wrong_link() -> None:
    t01 = {"Q1": {"en_label": "Yazılıkaya", "lat": 51.0, "lon": 0.0}}
    names = {"Q1": {"labels": {"en": "Yazılıkaya"}}}
    assert _name("Q1", "Yazılıkkaya", t01=t01, names=names)["class"] == "N6"
    far = {"Q1": {"en_label": "Kirkuk Citadel", "lat": 51.3, "lon": 0.0}}
    row = _name(
        "Q1", "Castle of Kirkûk", t01=far, names={"Q1": {"labels": {"en": "Kirkuk Citadel"}}}
    )
    assert (row["class"], row["group"]) == ("Q4", "wrong-link")


def test_a_shared_item_is_a_wrong_link_and_a_near_residual_is_read() -> None:
    t01 = {"Q1": {"en_label": "Paphos Archaeological Park", "lat": 51.0, "lon": 0.0}}
    names = {"Q1": {"labels": {"en": "Paphos Archaeological Park"}}}
    shared = _name("Q1", "House of Aion", t01=t01, names=names, shared={"Q1": 8})
    assert shared["class"] == "Q2"
    t01["Q1"]["instance_qids"] = ["Q532"]
    alone = _name("Q1", "House of Aion", t01=t01, names=names, labels={"Q532": "village"})
    assert (alone["class"], alone["group"], alone["n7"]) == ("N7", "review", "anchor-is-locality")


def test_an_item_without_a_coordinate_is_a_wrong_link_not_a_residual() -> None:
    t01 = {"Q1": {"en_label": "Iron Age", "lat": None, "lon": None}}
    row = _name("Q1", "Dun Cuier", t01=t01, names={"Q1": {"labels": {"en": "Iron Age"}}})
    assert (row["class"], row["group"]) == ("Q3", "wrong-link")
    assert any("has no P625" in e["quote"] for e in row["evidence"])


def test_a_kept_name_does_not_vouch_for_its_link() -> None:
    """Dolmens of Sardinia on Q101659 "dolmen" (the class), The Temple of Artemis stored in Greece on
    the Ephesus temple 388 km away, Asklepion (Kos) on an item Paphos shares: the name matches, the
    link is still wrong - reported, not hidden behind the name."""
    cls = _name(
        "Q101659",
        "Dolmens of Sardinia",
        t01={"Q101659": {"en_label": "dolmen", "lat": None, "lon": None}},
        names={"Q101659": {"labels": {"en": "dolmen"}, "sitelinks": {"lvwiki": "Dolmens"}}},
    )
    assert (cls["class"], cls["group"], cls["link_suspect"]) == ("N3", "keep", ["Q1"])
    assert any("has no P625" in e["quote"] for e in cls["evidence"])
    far = _name(
        "Q43018",
        "The Temple of Artemis",
        t01={"Q43018": {"en_label": "Temple of Artemis", "lat": 54.5, "lon": 0.0}},
        names={"Q43018": {"labels": {"en": "Temple of Artemis"}}},
        shared={"Q43018": 2},
    )
    assert (far["class"], far["group"], far["link_suspect"]) == ("N2", "keep", ["Q2", "Q4"])
    assert any("km from the stored point" in e["quote"] for e in far["evidence"])
    assert any("linked by 2 curated sites" in e["quote"] for e in far["evidence"])
    clean = _name(
        "Q1",
        "Hattusas",
        t01={"Q1": {"en_label": "Hattusa", "lat": 51.0, "lon": 0.0}},
        names={"Q1": {"labels": {"en": "Hattusa"}, "aliases": {"en": ["Hattusas"]}}},
    )
    assert clean["link_suspect"] == []


# ── the coordinate witnesses ──────────────────────────────────────────────────────────────────


def _w(kind: str, point: tuple[float, float], **kw: Any) -> C.Witness:
    """A witness on the grid its digits are written on, as `classify.witnesses` builds it."""
    kw.setdefault("step", C.grid_of(*point))
    return C.Witness(kind, point[0], point[1], f"https://example.org/{kind}", kind, **kw)


def test_calakmul_moves_to_the_item_where_wikidata_and_wikipedia_agree() -> None:
    """Wikidata's point is whole arcseconds, the article's 19.41" - no rounding of each other."""
    ws = [_w("enwiki", CALAKMUL_EN), _w("wikidata", CALAKMUL_WD, precision_m=15.5)]
    assert ws[1].step == pytest.approx(1 / 3600) and ws[0].step == 1e-8
    verdict = C.weigh(CALAKMUL_STORED, ws)
    assert verdict["verdict"] == "move"
    assert verdict["to"].kind == "wikidata" and verdict["agreeing"] == ["wikidata", "enwiki"]
    assert 40 < verdict["agreement_m"] < 60


def test_petroglyph_beach_counts_once_because_both_points_are_one_point() -> None:
    ws = [_w("wikidata", JUNEAU, precision_m=0.1), _w("enwiki", JUNEAU)]
    assert not C.independent(*ws)
    verdict = C.weigh(WRANGELL, ws)
    assert verdict["verdict"] == "review"
    assert verdict["reason"] == "the two witnesses are one: the same point (0 m apart, within 31 m)"


# Castro of Santa Trega and Khao Sam Kaeo as Wikidata and the article held them on 2026-09-23: the
# article's value is the item's cut to four decimals (5.6 m and 10.7 m apart).
CASTRO_WD, CASTRO_EN = (41.89275, -8.869808), (41.8927, -8.8698)
KHAO_WD, KHAO_EN = (10.52725, 99.18208333333334), (10.5272, 99.182)
# Taq Kasra: the article's 33°05'37", 44°34'51" is the item's point rounded to whole arcseconds.
TAQ_WD, TAQ_EN = (33.093722222222, 44.580722222222), (33.09361111, 44.58083333)


def test_an_article_that_holds_the_items_point_cut_short_is_not_a_second_witness() -> None:
    for wd, en, grid in (
        (CASTRO_WD, CASTRO_EN, "4 decimals"),
        (KHAO_WD, KHAO_EN, "4 decimals"),
        (TAQ_WD, TAQ_EN, "whole arcseconds"),
    ):
        a, b = _w("wikidata", wd), _w("enwiki", en)
        assert C.rounded_copy(a, b) == f"enwiki is wikidata rounded to {grid}"
        assert not C.independent(a, b)
        verdict = C.weigh((wd[0] + 0.05, wd[1]), [a, b])
        assert verdict["verdict"] == "review"
        assert (
            verdict["reason"] == f"the two witnesses are one: enwiki is wikidata rounded to {grid}"
        )


def test_a_rounded_copy_further_apart_than_an_arcsecond_is_still_one_witness() -> None:
    """Near the equator a value truncated to whole arcseconds on both axes lies up to 44 m from its
    source - further than the one-arcsecond floor, so only the rounding rule sees the copy."""
    whole = (1 / 3600, 10 + 1 / 3600)  # 0°00'01", 10°00'01"
    source = (1.9 / 3600, 10 + 1.9 / 3600)  # 0.9" more on each axis
    a, b = _w("wikidata", source), _w("enwiki", whole)
    assert b.step == pytest.approx(1 / 3600) and a.step == 0.0
    assert C._m(a, b) > C.same_point_m(a, b)
    assert C.rounded_copy(a, b) == "enwiki is wikidata rounded to whole arcseconds"
    assert not C.independent(a, b)
    # the same distance without the rounding is two witnesses
    moved = (whole[0] + 0.0000001, whole[1])
    assert C.independent(a, _w("enwiki", moved, step=0.0))


def test_one_point_within_an_arcsecond_is_one_witness() -> None:
    """Temple of Atargatis's item and article are 8 m apart, Eridu's 27 m: one point each, although
    neither value is the other rounded."""
    atargatis = (_w("wikidata", (34.746854, 40.731011)), _w("enwiki", (34.746918, 40.73105)))
    eridu = (_w("wikidata", (30.81583, 45.99583)), _w("enwiki", (30.81583333, 45.99611111)))
    for a, b in (atargatis, eridu):
        assert C.rounded_copy(a, b) is None
        assert C._m(a, b) < C.SAME_POINT_M
        assert not C.independent(a, b)
    assert 30.8 < C.SAME_POINT_M < 31.0


def test_a_point_given_to_three_decimals_cannot_confirm_another_within_its_step() -> None:
    """At 60° north 86 m apart - more than an arcsecond, less than one step of 0.001° (111 m) - and no
    rounding of each other: an article that coarse cannot tell the two points apart."""
    a, b = _w("wikidata", (60.1232, 20.4545)), _w("enwiki", (60.123, 20.456))
    assert b.step == 0.001 and C.rounded_copy(a, b) is None
    assert C.SAME_POINT_M < C._m(a, b) < 0.001 * C.METRES_PER_DEGREE
    assert not C.independent(a, b)


def test_a_coarse_wikidata_precision_makes_two_points_one() -> None:
    """A P625 that declares 0.01° (±556 m) cannot confirm an article 394 m away."""
    a = _w("wikidata", (50.123456, 10.123456), precision_m=C.precision_m(0.01))
    b = _w("enwiki", (50.127, 10.123456))
    assert C.rounded_copy(a, b) is None and 300 < C._m(a, b) < 500
    assert not C.independent(a, b)
    assert C.independent(_w("wikidata", (50.123456, 10.123456)), b)


def test_the_tolerance_widens_with_a_coarse_wikidata_precision() -> None:
    """T01's floor: a P625 of precision 0.1° is uncertain by 5.6 km, so a stored point 2 km off it is
    where the item says, not a defect."""
    item = _w("wikidata", (50.123456, 10.123456), precision_m=C.precision_m(0.1))
    assert C.tolerance_m([item]) == pytest.approx(C.precision_m(0.1))
    verdict = C.weigh((50.141456, 10.123456), [item])
    assert verdict["verdict"] == "stored-agrees"


def test_a_p625_imported_from_english_wikipedia_is_not_a_second_witness() -> None:
    near = (CALAKMUL_WD[0] + 0.0004, CALAKMUL_WD[1])  # 44 m apart, so not "the same point"
    ws = [_w("wikidata", CALAKMUL_WD, derived_from="enwiki"), _w("enwiki", near)]
    assert not C.independent(*ws)
    assert "imported from English Wikipedia" in C.weigh(CALAKMUL_STORED, ws)["reason"]


def test_a_witness_at_the_stored_point_forbids_a_move() -> None:
    ws = [_w("wikidata", CALAKMUL_WD), _w("enwiki", CALAKMUL_STORED)]
    assert C.weigh(CALAKMUL_STORED, ws)["verdict"] == "stored-agrees"
    one = C.weigh(CALAKMUL_STORED, [_w("wikidata", CALAKMUL_WD)])
    assert (one["verdict"], one["reason"]) == ("review", "one witness only (wikidata)")


def test_a_pair_that_agrees_elsewhere_while_one_of_them_is_at_the_stored_point_is_read() -> None:
    stored = (50.0, 10.0)
    ws = [_w("wikidata", (50.008, 10.0)), _w("enwiki", (50.0125, 10.0))]  # 0.9 km and 1.4 km
    verdict = C.weigh(stored, ws)
    assert verdict["verdict"] == "review"
    assert verdict["reason"].endswith("wikidata puts the site at the stored point")


def test_a_p625_reference_to_english_wikipedia_is_read_from_its_references() -> None:
    entity = {
        "claims": {
            "P625": [
                {
                    "rank": "normal",
                    "mainsnak": {
                        "datavalue": {
                            "value": {
                                "latitude": 1.5,
                                "longitude": 2.5,
                                "precision": 1e-06,
                                "globe": "http://www.wikidata.org/entity/Q2",
                            }
                        }
                    },
                    "references": [{"snaks": {"P143": [{"datavalue": {"value": {"id": "Q328"}}}]}}],
                }
            ],
            "P189": [{"rank": "normal", "mainsnak": {"datavalue": {"value": {"id": "Q9"}}}}],
        },
        "sitelinks": {"enwiki": {"title": "Somewhere"}},
    }
    record = K.claims_record(entity)
    assert record["p625"]["references"] == {"P143": ["Q328"]} and record["p189"] == ["Q9"]
    assert C._p625_from_enwiki(record["p625"]["references"])
    assert record["enwiki"] == "Somewhere"


def test_a_p625_whose_import_url_is_english_wikipedia_is_not_a_second_witness() -> None:
    url = "https://en.wikipedia.org/w/index.php?title=Calakmul&oldid=1"
    assert C._p625_from_enwiki({"P4656": [url]})
    assert not C._p625_from_enwiki({"P4656": ["https://fr.wikipedia.org/w/index.php?oldid=1"]})
    claims = {"Q1": _claims("Q1", CALAKMUL_WD, enwiki="Calakmul", references={"P4656": [url]})}
    ws, _ = C.witnesses(
        "Q1", claims=claims, enwiki={"Calakmul": _page("Q1", "Calakmul", CALAKMUL_EN)}
    )
    assert ws[0].derived_from == "enwiki" and not C.independent(*ws)


WD_ENTITY = "http://www.wikidata.org/entity/"


def _p625_statement(rank: str, lat: float, lon: float) -> dict[str, Any]:
    value = {"latitude": lat, "longitude": lon, "precision": 1e-06, "globe": f"{WD_ENTITY}Q2"}
    return {"rank": rank, "mainsnak": {"datavalue": {"value": value}}}


def test_the_witness_is_the_preferred_p625_and_never_a_deprecated_one() -> None:
    """Charax Spasinu's item holds three P625, the second preferred and 1.07 km from the first."""
    charax = {
        "claims": {
            "P625": [
                _p625_statement("normal", 30.894692, 47.578031),
                _p625_statement("preferred", 30.89786289707795, 47.567476326068245),
                _p625_statement("normal", 30.9, 47.6),
            ]
        }
    }
    point = K.claims_record(charax)["p625"]
    assert (point["lat"], point["rank"], point["statements"]) == (30.89786289707795, "preferred", 3)
    stale = {
        "claims": {
            "P625": [
                _p625_statement("deprecated", 1.0, 1.0),
                _p625_statement("normal", 2.0, 2.0),
            ]
        }
    }
    point = K.claims_record(stale)["p625"]
    assert (point["lat"], point["rank"], point["statements"]) == (2.0, "normal", 1)


# ── one coordinate case end to end ───────────────────────────────────────────────────────────


def _claims(qid: str, point: tuple[float, float] | None, **kw: Any) -> dict[str, Any]:
    return {
        "missing": False,
        "en_label": kw.get("label"),
        "p625": None
        if point is None
        else {
            "lat": point[0],
            "lon": point[1],
            "precision": kw.get("precision", 1e-06),
            "globe": kw.get("globe", "Q2"),
            "rank": "normal",
            "references": kw.get("references", {}),
            "statements": 1,
        },
        "p31": kw.get("p31", ["Q839954"]),
        "p189": kw.get("p189", []),
        "p195": kw.get("p195", []),
        "p276": kw.get("p276", []),
        "enwiki": kw.get("enwiki"),
    }


def _page(qid: str, title: str, point: tuple[float, float]) -> dict[str, Any]:
    return {
        "title": title,
        "redirected": False,
        "missing": False,
        "wikibase_item": qid,
        "lat": point[0],
        "lon": point[1],
        "globe": "earth",
    }


def _coordinate(
    site: Mapping[str, Any], claims: Mapping[str, Any], enwiki: Mapping[str, Any], **kw
):
    return C.classify_coordinate(
        site,
        site["qid"],
        origin="T01/coords",
        claims=claims,
        labels={"Q839954": "archaeological site", "Q532": "village"},
        names=kw.pop("names", {"Q1": {"labels": {"en": site["name"]}}}),
        enwiki=enwiki,
        shared=kw.pop("shared", {}),
    )


def test_calakmul_end_to_end_is_a_move_with_its_witnesses() -> None:
    site = _site("Calakmul", "Q1", CALAKMUL_STORED)
    claims = {"Q1": _claims("Q1", CALAKMUL_WD, enwiki="Calakmul")}
    row = _coordinate(site, claims, {"Calakmul": _page("Q1", "Calakmul", CALAKMUL_EN)})
    assert row["verdict"] == "move" and row["new"]["from"] == "wikidata"
    assert row["moved_km"] > 900
    assert {w["kind"] for w in row["witnesses"]} == {"wikidata", "enwiki"}


def test_an_item_that_is_not_the_site_is_never_a_witness() -> None:
    site = _site("Calakmul", "Q1", CALAKMUL_STORED)
    enwiki = {"Calakmul": _page("Q1", "Calakmul", CALAKMUL_EN)}
    shared = _coordinate(
        site, {"Q1": _claims("Q1", CALAKMUL_WD, enwiki="Calakmul")}, enwiki, shared={"Q1": 2}
    )
    assert (shared["verdict"], shared["class"]) == ("not-comparable", "shared-item")
    village = _coordinate(
        site, {"Q1": _claims("Q1", CALAKMUL_WD, enwiki="Calakmul", p31=["Q532"])}, enwiki
    )
    assert (village["verdict"], village["class"]) == ("not-comparable", "container-item")
    other = _coordinate(
        site,
        {"Q1": _claims("Q1", CALAKMUL_WD, enwiki="Calakmul")},
        enwiki,
        names={"Q1": {"labels": {"en": "Calakmul Biosphere Reserve"}}},
    )
    assert (other["verdict"], other["class"]) == ("not-comparable", "item-is-not-the-site")


def test_a_road_or_a_wall_is_a_line_whose_point_is_an_arbitrary_spot() -> None:
    site = _site("Via Egnatia", "Q1", CALAKMUL_STORED)
    claims = {"Q1": _claims("Q1", CALAKMUL_WD, enwiki="Via Egnatia", p31=["Q2143825"])}
    enwiki = {"Via Egnatia": _page("Q1", "Via Egnatia", CALAKMUL_EN)}
    row = C.classify_coordinate(
        site,
        "Q1",
        origin="T01/coords",
        claims=claims,
        labels={"Q2143825": "Roman road"},
        names={"Q1": {"labels": {"en": "Via Egnatia"}}},
        enwiki=enwiki,
        shared={},
    )
    assert (row["verdict"], row["class"]) == ("not-comparable", "linear-or-areal-item")
    assert "new" not in row


def _one_witness(enwiki_page: dict[str, Any], **claims_kw: Any) -> dict[str, Any]:
    site = _site("Calakmul", "Q1", CALAKMUL_STORED)
    claims = {"Q1": _claims("Q1", CALAKMUL_WD, enwiki="Calakmul", **claims_kw)}
    return _coordinate(site, claims, {"Calakmul": enwiki_page})


def test_an_article_is_a_witness_only_for_its_own_item_on_earth() -> None:
    """Pyramid of Neferhetepes redirects to the Pyramid of Userkaf: that article's point is another
    item's, and a missing page or a point on another globe says nothing about this site."""
    own = _page("Q1", "Calakmul", CALAKMUL_EN)
    for page, note in (
        ({**own, "wikibase_item": "Q2"}, "no English article of Q1"),
        ({**own, "missing": True}, "no English article of Q1"),
        ({**own, "globe": "moon"}, "carries no Earth coordinates"),
    ):
        row = _one_witness(page)
        assert (row["verdict"], row["reason"]) == ("review", "one witness only (wikidata)")
        assert any(note in n for n in row["witness_notes"]), row["witness_notes"]


def test_the_witnesses_carry_the_grid_their_digits_are_written_on() -> None:
    """End to end: El Kab's item holds 25°07', 32°48' - its article's 25°07'08", 32°47'52" cut to
    whole arcminutes, 333 m away - and an article of whole arcseconds truncated from its item's point
    lies 39 m from it near the equator. Both pairs are one witness, so neither site moves."""
    el_kab = _site("El Kab", "Q1", (25.35, 32.8))
    claims = {"Q1": _claims("Q1", (25.116666666667, 32.8), enwiki="El Kab")}
    pages = {"El Kab": _page("Q1", "El Kab", (25.11888889, 32.79777778))}
    ws, _ = C.witnesses("Q1", claims=claims, enwiki=pages)
    assert [w.step for w in ws] == [1 / 60, 1 / 3600]
    assert "(given to whole arcseconds)" in ws[1].quote
    row = _coordinate(el_kab, claims, pages)
    assert row["verdict"] == "review"
    assert (
        row["reason"] == "the two witnesses are one: wikidata is enwiki rounded to whole arcminutes"
    )
    equator = _site("Equator", "Q1", (0.3, 10.0))
    claims = {"Q1": _claims("Q1", (1.9 / 3600, 10 + 1.9 / 3600), enwiki="Equator")}
    pages = {"Equator": _page("Q1", "Equator", (1 / 3600, 10 + 1 / 3600))}
    row = _coordinate(equator, claims, pages)
    assert row["verdict"] == "review"
    assert (
        row["reason"] == "the two witnesses are one: enwiki is wikidata rounded to whole arcseconds"
    )


def test_a_p625_on_another_globe_is_no_witness() -> None:
    row = _one_witness(_page("Q1", "Calakmul", CALAKMUL_EN), globe="Q405")
    assert (row["verdict"], row["reason"]) == ("review", "one witness only (enwiki)")
    assert row["witness_notes"] == ["Q1 P625 is on globe Q405"]


MUSEUM = (48.8611, 2.3358)
FIND = (27.629712, 38.549421)


def _museum_case(stored: tuple[float, float]) -> dict[str, Any]:
    site = _site("Tayma Stele", "Q1", stored)
    claims = {
        "Q1": _claims("Q1", MUSEUM, p189=["Q2"], p195=["Q3"]),
        "Q2": _claims("Q2", FIND, enwiki="Tayma"),
        "Q3": _claims("Q3", MUSEUM),
    }
    enwiki = {"Tayma": _page("Q2", "Tayma", (FIND[0] + 0.002, FIND[1]))}
    return _coordinate(site, claims, enwiki)


def test_a_museum_object_stored_at_its_museum_moves_to_its_find_spot() -> None:
    row = _museum_case(MUSEUM)
    assert (row["verdict"], row["rule"]) == ("move", "museum-find-spot")
    assert (row["new"]["lat"], row["new"]["lon"]) == FIND
    assert row["museum"]["stored_at_holder"] == ["Q3"]


def test_a_museum_object_stored_elsewhere_is_never_moved_to_the_find_spot() -> None:
    row = _museum_case((30.0, 30.0))
    assert row["verdict"] == "review" and "not at its holding museum" in row["reason"]
    assert "new" not in row


def test_the_pergamon_altar_stays_at_pergamon() -> None:
    row = _museum_case((FIND[0] + 0.002, FIND[1]))
    assert row["verdict"] == "stored-agrees"


def test_an_object_with_two_find_spots_names_no_find_spot() -> None:
    """Two P189 values are two places: neither is *the* find-spot, so the museum rule does not apply
    and the item's own point is judged like any other."""
    claims = {
        "Q1": _claims("Q1", MUSEUM, p189=["Q2", "Q4"], p195=["Q3"]),
        "Q2": _claims("Q2", FIND),
        "Q3": _claims("Q3", MUSEUM),
        "Q4": _claims("Q4", (FIND[0] + 1.0, FIND[1])),
    }
    assert C.museum_object("Q1", claims) is None
    row = _coordinate(_site("Tayma Stele", "Q1", MUSEUM), claims, {})
    assert "museum" not in row and row["rule"] == "two-independent-witnesses"


# ── B2 on a schematic map ─────────────────────────────────────────────────────────────────────


def _atlas() -> tuple[list[str], list[Any], shapely.STRtree]:
    names = ["Italy", "Greece", "Russia", "United Kingdom"]
    geoms = [box(10, 40, 15, 45), box(20, 35, 25, 40), box(32, 44, 37, 47), box(-8, 54, -5, 55)]
    return names, geoms, shapely.STRtree(geoms)


def _b2(stored: str, point: tuple[float, float], contained: str, **kw: Any) -> dict[str, Any]:
    finding = {
        "site_id": SITE,
        "current_value": stored,
        "evidence": [
            {"quote": f"point outside by {kw.get('km', 30.0)} km; contained in {contained}"}
        ],
    }
    site = _site(
        "X", kw.get("qid"), point, country=kw.get("now", stored), description=kw.get("description")
    )
    t01 = kw.get("t01", {})
    return C.classify_b2(finding, site, t01=t01, p17_labels=kw.get("labels", {}), atlas=_atlas())


def test_the_b2_classes_follow_the_owner_decisions() -> None:
    assert _b2("Ukraine", (45.0, 34.0), "Russia")["class"] == "c1"  # Crimea, B10
    assert _b2("Northern Ireland", (54.6, -6.0), "no country polygon")["class"] == "c3"
    ni = _b2("Ireland", (54.6, -6.0), "United Kingdom", now="Northern Ireland")
    assert (ni["class"], ni["state"]) == (
        "b-ni",
        "written since the census: 'Ireland' -> 'Northern Ireland'",
    )
    assert _b2("Baltic Sea", (55.0, 18.0), "no country polygon (open water)")["class"] == "d"
    assert _b2("Italy", (40.5, 14.2), "no country polygon (open water)", km=1.2)["class"] == "c2"
    wrong = _b2(
        "Germany",
        (35.1, 24.0),
        "Greece",
        qid="Q1",
        t01={"Q1": {"lat": 35.11, "lon": 24.0, "country_qids": ["Q41"]}},
        labels={"Q41": "Greece"},
    )
    assert (wrong["class"], wrong["state"]) == ("b", "open")


def test_a_site_whose_own_text_spans_the_border_is_not_a_wrong_country() -> None:
    """The Côa Valley and Siega Verde rock art: P17 names Portugal only and the point lies in it, but
    the row's own description spans Portugal and Spain - writing either country alone is wrong."""
    kw = {
        "qid": "Q1",
        "t01": {"Q1": {"lat": 35.11, "lon": 24.0, "country_qids": ["Q41"]}},
        "labels": {"Q41": "Greece"},
    }
    spanning = "A transboundary site spanning the valley in Greece and its continuation in Italy."
    row = _b2("Italy", (35.1, 24.0), "Greece", description=spanning, **kw)
    assert (row["class"], row["route"]) == ("c2", C.B2_ROUTE["c2"])
    assert (
        _b2("Italy", (35.1, 24.0), "Greece", description="A site in Greece.", **kw)["class"] == "b"
    )


def test_a_move_into_another_country_is_reported_and_crimea_keeps_ukraine() -> None:
    moved = C.country_after_move("Lebanon", 36.0, 22.0, _atlas())
    assert moved == {"stored": "Lebanon", "polygon": ["Greece"], "agrees": False, "note": None}
    crimea = C.country_after_move("Ukraine", 45.0, 34.0, _atlas())
    assert crimea["agrees"] and "B10" in crimea["note"]


# ── duplicates ────────────────────────────────────────────────────────────────────────────────


def _dup_site(sid: str, name: str, lat: float, links: int, **kw: Any) -> dict[str, Any]:
    return {
        "id": sid,
        "name": name,
        "lat": lat,
        "lon": -6.2,
        "qid": kw.get("qid", "Q1242421"),
        "n_links": links,
        "n_ext": kw.get("n_ext", 2),
        "n_img": kw.get("n_img", 3),
        "source_url": "https://en.wikipedia.org/wiki/X",
        "created_at": kw.get("created", "2026-03-04"),
        "country": "Northern Ireland",
        "lat_text": str(lat),
        "lon_text": "-6.2",
    }


DOOEY = {
    "Q1242421": {
        "labels": {"en": "Ballymacaldrack Court Tomb"},
        "aliases": {"en": ["Dooey's Cairn"]},
    }
}


def test_dooeys_cairn_and_ballymacaldrack_are_one_tomb_and_the_richer_row_survives() -> None:
    sites = {
        SITE: _dup_site(SITE, "Dooey's Cairn", 54.94, 0),
        OTHER: _dup_site(OTHER, "Ballymacaldrack Court Tomb", 54.94006, 5),
    }
    pairs = C.classify_pairs(sites, DOOEY)
    assert [p["class"] for p in pairs] == ["DUP"]
    lines, unresolved, held = C.duplicate_groups(pairs, sites)
    assert unresolved == [] and held == []
    assert [(line["loser_id"], line["survivor_id"]) for line in lines] == [(SITE, OTHER)]
    assert set(lines[0]) == {"loser_id", "survivor_id", "evidence"}
    assert "more content links" in lines[0]["evidence"][1]["quote"]


def test_the_survivor_rule_is_links_then_sources_then_age_then_id() -> None:
    a, b = _dup_site(SITE, "A", 1.0, 5), _dup_site(OTHER, "B", 1.0, 5)
    assert C.survivor_key(a) < C.survivor_key(b)  # a full tie: the lower id, and only that
    b["n_ext"] = 3
    assert C.survivor_key(b) < C.survivor_key(a)
    b["n_ext"], a["created_at"] = 2, "2026-03-05"
    assert C.survivor_key(b) < C.survivor_key(a)
    assert C._decisive_step(a, b) == "older created_at"


def test_one_name_only_is_part_of_and_far_apart_is_a_wrong_item() -> None:
    names = {"Q1242421": {"labels": {"en": "Ballymacaldrack Court Tomb"}}}
    sites = {
        SITE: _dup_site(SITE, "Dooey's Cairn", 54.94, 0),
        OTHER: _dup_site(OTHER, "Ballymacaldrack Court Tomb", 54.94006, 5),
    }
    assert [p["class"] for p in C.classify_pairs(sites, names)] == ["PART-OF"]
    sites[OTHER]["lat"] = 55.0
    assert [p["class"] for p in C.classify_pairs(sites, DOOEY)] == ["WRONG-ID"]


def test_a_name_of_generic_words_only_is_no_name_of_the_item() -> None:
    names = {"Q1": {"labels": {"en": "Archaeological Site"}}}
    sites = {
        SITE: _dup_site(SITE, "Ancient Site", 1.0, 0, qid="Q1"),
        OTHER: _dup_site(OTHER, "Archaeological Ruins", 1.0, 0, qid="Q1"),
    }
    assert [p["class"] for p in C.classify_pairs(sites, names)] == ["NEITHER"]


def test_a_group_whose_members_are_not_all_duplicates_is_left_unresolved() -> None:
    sites = {
        SITE: _dup_site(SITE, "Dooey's Cairn", 54.94, 0),
        OTHER: _dup_site(OTHER, "Ballymacaldrack Court Tomb", 54.94006, 5),
        THIRD: _dup_site(THIRD, "Dooey's Cairn", 54.94012, 1),
    }
    pairs = [
        {"class": "DUP", "a": SITE, "b": OTHER, "qid": "Q1242421", "distance_m": 7.0},
        {"class": "DUP", "a": OTHER, "b": THIRD, "qid": "Q1242421", "distance_m": 7.0},
        {"class": "PART-OF", "a": SITE, "b": THIRD, "qid": "Q1242421", "distance_m": 14.0},
    ]
    lines, unresolved, held = C.duplicate_groups(pairs, sites)
    assert lines == [] and held == [] and unresolved == [sorted([SITE, OTHER, THIRD])]


def test_one_site_recorded_on_two_sides_of_a_border_is_held_for_the_owner() -> None:
    """Banias (Syria) and Caesarea Philippi (Israel) are one site on one item, 290 m apart - but
    retiring either row would settle the Golan line the owner decided to leave (B10)."""
    names = {"Q606295": {"labels": {"en": "Banias"}, "aliases": {"en": ["Caesarea Philippi"]}}}
    sites = {
        SITE: {**_dup_site(SITE, "Banias", 33.2487, 4, qid="Q606295"), "country": "Syria"},
        OTHER: {
            **_dup_site(OTHER, "Caesarea Philippi", 33.2465, 5, qid="Q606295"),
            "country": "Israel",
        },
    }
    pairs = C.classify_pairs(sites, names)
    assert [p["class"] for p in pairs] == ["DUP"]
    lines, unresolved, held = C.duplicate_groups(pairs, sites)
    assert lines == [] and unresolved == []
    assert [(h["site_ids"], h["countries"], h["survivor_by_rule"]) for h in held] == [
        (sorted([SITE, OTHER]), ["Israel", "Syria"], OTHER)
    ]
    assert "B10" in held[0]["reason"] and held[0]["lines"][0]["loser_id"] == SITE


# ── what is fetched ───────────────────────────────────────────────────────────────────────────


class FakeNet:
    """`census.fetch.Fetcher.get_json`'s signature and nothing else: an unknown keyword raises."""

    def __init__(self, answers: list[dict[str, Any]]) -> None:
        self.answers = list(answers)
        self.calls: list[tuple[str, dict[str, Any], str, bool]] = []

    def get_json(
        self, url: str, params: dict[str, Any] | None = None, ns: str = "json", force: bool = False
    ) -> dict[str, Any]:
        self.calls.append((url, dict(params or {}), ns, force))
        return {"json": self.answers.pop(0)}


def test_a_busy_api_is_asked_again_past_the_cache_and_a_refusal_raises() -> None:
    busy = {"error": {"code": "cirrussearch-too-busy-error"}}
    net = FakeNet([busy, {"query": {}}])
    assert K.api_json(net, K.WIKIDATA_API, {"a": "b"}, ns="x", pause=0) == {"query": {}}
    assert [call[3] for call in net.calls] == [False, True]
    with pytest.raises(inputs.InputError, match="stayed busy"):
        K.api_json(FakeNet([busy] * K.TRANSIENT_ATTEMPTS), K.WIKIDATA_API, {}, ns="x", pause=0)
    with pytest.raises(inputs.InputError, match="refused"):
        K.api_json(
            FakeNet([{"error": {"code": "no-such-entity"}}]), K.WIKIDATA_API, {}, ns="x", pause=0
        )


def test_wikipedia_coordinates_are_asked_for_every_page_and_a_partial_answer_raises() -> None:
    page = {
        "title": "Calakmul",
        "pageprops": {"wikibase_item": "Q1"},
        "coordinates": [{"lat": 18.1, "lon": -89.8, "globe": "earth"}],
    }
    net = FakeNet([{"query": {"pages": [page]}}])
    got = K.fetch_enwiki_coords(net, ["Calakmul"])
    assert got["Calakmul"]["lat"] == 18.1 and net.calls[0][1]["colimit"] == "max"
    partial = FakeNet([{"continue": {"cocontinue": "1|2"}, "query": {"pages": [page]}}])
    with pytest.raises(inputs.InputError, match="in part"):
        K.fetch_enwiki_coords(partial, ["Calakmul"])


def test_an_answer_that_is_not_a_json_object_is_refused() -> None:
    for body in (None, ["a list"], "text"):
        with pytest.raises(inputs.InputError, match="no JSON object"):
            K.api_json(FakeNet([body]), K.WIKIDATA_API, {}, ns="x", pause=0)  # type: ignore[list-item]


def test_wikidata_must_answer_for_every_item_asked() -> None:
    with pytest.raises(inputs.InputError, match="without an `entities` map"):
        K.fetch_names(FakeNet([{"success": 1}]), ["Q1"])
    with pytest.raises(inputs.InputError, match="did not answer for"):
        K.fetch_names(FakeNet([{"entities": {"Q1": {"labels": {}}}}]), ["Q1", "Q2"])
    got = K.fetch_names(FakeNet([{"entities": {"Q1": {}, "Q2": {"missing": ""}}}]), ["Q2", "Q1"])
    assert (got["Q1"]["missing"], got["Q2"]["missing"]) == (False, True)


def test_wikipedia_must_answer_for_every_title_asked() -> None:
    with pytest.raises(inputs.InputError, match="without a `query`"):
        K.fetch_enwiki_coords(FakeNet([{"batchcomplete": True}]), ["Calakmul"])
    other = {"title": "Tikal", "pageprops": {"wikibase_item": "Q2"}}
    with pytest.raises(inputs.InputError, match="did not answer for 'Calakmul'"):
        K.fetch_enwiki_coords(FakeNet([{"query": {"pages": [other]}}]), ["Calakmul", "Tikal"])


def test_the_research_refuses_an_answer_without_its_list() -> None:
    with pytest.raises(inputs.InputError, match="answered without `geosearch`"):
        R.neighbours(FakeNet([{"query": {}}]), 1.0, 2.0)
    assert R.neighbours(FakeNet([{"query": {"geosearch": [{"title": "Q7"}]}}]), 1.0, 2.0) == ["Q7"]
    with pytest.raises(inputs.InputError, match="answered without `search`"):
        R.search(FakeNet([{"searchinfo": {}}]), "Dun Cuier")
    assert R.search(FakeNet([{"search": [{"id": "Q8"}]}]), "Dun Cuier") == ["Q8"]


def test_a_cache_file_that_is_missing_or_not_derived_is_refused(tmp_path: Path) -> None:
    with pytest.raises(inputs.InputError, match="is missing - `run.py collect` writes it"):
        inputs.read_cache(tmp_path / "wd_names.json")
    (tmp_path / "raw.json").write_text(json.dumps({"entities": {}}), encoding="utf-8")
    with pytest.raises(inputs.InputError, match="no `records` map"):
        inputs.read_cache(tmp_path / "raw.json")
    inputs.write_cache(tmp_path / "ok.json", {"Q1": {"a": 1}}, {"fetched_at": "now"})
    assert inputs.read_cache(tmp_path / "ok.json") == {"Q1": {"a": 1}}


def test_a_census_link_held_twice_is_refused_not_overwritten(tmp_path: Path) -> None:
    (tmp_path / "snapshot").mkdir()
    rows = [
        {"site_id": SITE, "kind": "wikidata_qid", "value": "Q1"},
        {"site_id": SITE, "kind": "enwiki_title", "value": "Calakmul"},
        {"site_id": SITE, "kind": "wikidata_qid", "value": "Q2"},
    ]
    with gzip.open(
        tmp_path / "snapshot" / "site_external_ids.jsonl.gz", "wt", encoding="utf-8"
    ) as f:
        f.write("".join(json.dumps(r) + "\n" for r in rows))
    with pytest.raises(inputs.InputError, match="carries two wikidata_qid rows"):
        inputs.load_census_links(tmp_path)
    with gzip.open(
        tmp_path / "snapshot" / "site_external_ids.jsonl.gz", "wt", encoding="utf-8"
    ) as f:
        f.write("".join(json.dumps(r) + "\n" for r in rows[:2]))
    assert inputs.load_census_links(tmp_path) == {
        SITE: {"wikidata_qid": "Q1", "enwiki_title": "Calakmul"}
    }


def test_a_short_export_is_refused_not_classified(tmp_path: Path) -> None:
    with pytest.raises(inputs.InputError, match="curated rows, not 5004"):
        K.export(tmp_path, reader=lambda sql: [{"id": SITE}])
    assert not (tmp_path / inputs.EXPORT_FILE).exists()


# ── the coordinate plan ───────────────────────────────────────────────────────────────────────


def _move(sid: str = SITE, *, agreeing: tuple[str, ...] = ("wikidata", "enwiki")) -> dict[str, Any]:
    return {
        "site_id": sid,
        "name": "Calakmul",
        "verdict": "move",
        "agreeing": list(agreeing),
        "new": {"lat": CALAKMUL_WD[0], "lon": CALAKMUL_WD[1]},
        "lat_text": "19.243221692240958",
        "lon_text": "-98.34002245550043",
        "geom_text": "0101000020E6100000AAAA",
        "stored": list(CALAKMUL_STORED),
        "moved_km": 907.3,
        "witnesses": [
            {
                "kind": "wikidata",
                "quote": "P625 = 18.105",
                "url": "https://www.wikidata.org/wiki/Q1",
            },
            {"kind": "enwiki", "quote": "enwiki", "url": "https://en.wikipedia.org/wiki/Calakmul"},
        ],
        "reason": "agree",
        "tolerance_m": 1000.0,
        "rule": "two-independent-witnesses",
    }


def test_a_move_is_three_journalled_changes_and_the_geom_is_the_new_point() -> None:
    rows = P.changes([_move(), {"site_id": OTHER, "verdict": "review"}])
    assert [r.column for r in rows] == ["geom", "lat", "lon"]
    by = {r.column: r for r in rows}
    assert by["lat"].new_value == "18.105" and float(by["lon"].new_value) == CALAKMUL_WD[1]
    assert by["geom"].new_value == f"SRID=4326;POINT({CALAKMUL_WD[1]!r} 18.105)"
    assert by["lat"].old_value == "19.243221692240958"
    assert len({r.change_key for r in rows}) == 3


def test_a_move_needs_two_witnesses_a_geom_a_real_change_and_a_point_on_earth() -> None:
    with pytest.raises(P.PlanError, match="two agreeing witnesses"):
        P.changes([_move(agreeing=("wikidata",))])
    with pytest.raises(P.PlanError, match="no geom"):
        P.changes([{**_move(), "geom_text": None}])
    same = {**_move(), "new": {"lat": 19.243221692240958, "lon": -98.34002245550043}}
    with pytest.raises(P.PlanError, match="not a change"):
        P.changes([same])
    with pytest.raises(P.PlanError, match="not a point on Earth"):
        P.changes([{**_move(), "new": {"lat": 95.0, "lon": 1.0}}])


def test_a_plan_names_each_site_once_and_by_its_uuid() -> None:
    with pytest.raises(P.PlanError, match="is not a UUID"):
        P.changes([_move(sid="11111111-1111-4111-8111-11111111111'; DROP TABLE x; --")])
    with pytest.raises(P.PlanError, match="is planned twice"):
        P.changes([_move(), _move()])
    assert len(P.changes([_move(), _move(OTHER)])) == 6


def test_a_statement_moves_whole_sites_only() -> None:
    rows = P.changes([_move()])
    with pytest.raises(P.PlanError, match="are not 3 columns per site"):
        P.render(rows[:2], reversal=False)
    with pytest.raises(P.PlanError, match="no rows"):
        P.render([], reversal=False)


def test_the_read_names_its_sites_by_uuid_only() -> None:
    bad = P.Change(
        site_id="1 OR 1=1",
        name="x",
        column="lat",
        old_value="1",
        new_value="2",
        evidence=(),
        change_key="k",
    )
    with pytest.raises(P.PlanError, match="is not a UUID"):
        P.read_rows([bad], reader=lambda sql: pytest.fail(f"sent {sql}"))


def _live(rows: list[P.Change], state: str, **override: Any) -> dict[str, dict[str, Any]]:
    by = {r.column: r for r in rows}
    pick = "old_value" if state == "old" else "new_value"
    row = {
        "site_id": SITE,
        "lat": getattr(by["lat"], pick),
        "lon": getattr(by["lon"], pick),
        "geom": getattr(by["geom"], pick),
        "geom_is_point": True,
    }
    return {SITE: {**row, **override}}


def test_check_and_verify_compare_every_column_and_the_geometry() -> None:
    rows = P.changes([_move()])
    assert P.compare(rows, _live(rows, "old"), want="old") == []
    assert P.compare(rows, _live(rows, "new"), want="new") == []
    moved_by_hand = P.compare(rows, _live(rows, "old", lat="19.25"), want="old")
    assert moved_by_hand == ["Calakmul lat: expected 19.243221692240958, found 19.25"]
    other_geom = P.compare(rows, _live(rows, "old", geom="0101000020E61000BBBB"), want="old")
    assert other_geom == [
        "Calakmul geom: expected '0101000020E6100000AAAA', found '0101000020E61000BBBB'"
    ]
    stale = P.compare(rows, _live(rows, "new", geom_is_point=False), want="new")
    assert stale == ["Calakmul geom: not the point lat/lon names"]
    assert P.compare(rows, {}, want="new") == ["Calakmul: the site is not in production"] * 3


def test_the_statement_is_guarded_and_every_change_goes_through_the_primitive() -> None:
    rows = P.changes([_move()])
    sql = P.render(rows, reversal=False)
    assert sql.startswith("-- Generated by scripts/remediation/bcases/coord_plan.py")
    assert f"-- plan sha256 {P.plan_digest(rows)}" in sql
    assert sql.rstrip().count("COMMIT;") == 1 and "\nROLLBACK;" not in sql
    assert "SET LOCAL lock_timeout = '10s';" in sql
    assert f"SET LOCAL statement_timeout = '{P.STATEMENT_TIMEOUT}';" in sql
    assert "     WHERE u.id IS NULL OR u.source_id <> 'ancient_nerds';" in sql
    assert (
        "HAVING array_agg(column_name ORDER BY column_name) <> ARRAY['geom', 'lat', 'lon']" in sql
    )
    # guard 3: every column still holds its planned old value, compared in its own type
    guard = sql[sql.index("-- guard 3") : sql.index("-- guard 4")]
    for clause in (
        "(p.column_name = 'lat' AND u.lat IS DISTINCT FROM p.old_value::double precision)",
        "(p.column_name = 'lon' AND u.lon IS DISTINCT FROM p.old_value::double precision)",
        "(p.column_name = 'geom' AND u.geom IS DISTINCT FROM p.old_value::geometry)",
    ):
        assert clause in guard, clause
    assert "g.new_value::geometry IS DISTINCT FROM" in sql
    assert "moved := moved + apply_remediation_change(" in sql
    assert "'unified_sites', r.column_name, 'id', r.site_id::text," in sql
    assert f"'{P.TEST_ID}', '{P.RUN_STAMP}', r.change_key, 'two_source'" in sql
    assert "IF moved <> expected THEN" in sql
    # invariant 1: the site holds the new point, and a geom that is that point
    invariant = sql[sql.index("-- invariant 1") : sql.index("-- invariant 2")]
    for clause in (
        "(p.column_name = 'lat' AND u.lat IS DISTINCT FROM p.new_value::double precision)",
        "(p.column_name = 'lon' AND u.lon IS DISTINCT FROM p.new_value::double precision)",
        "(p.column_name = 'geom' AND u.geom IS DISTINCT FROM\n"
        "            ST_SetSRID(ST_MakePoint(u.lon, u.lat), 4326));",
    ):
        assert clause in invariant, clause
    assert "outside the plan', bad;" in sql and "no matching journal row', bad;" in sql
    for says in (
        "% row(s) are not curated sites', bad;",
        "% site(s) do not move geom, lat and lon together', bad;",
        "% row(s) no longer hold the planned old value', bad;",
        "% planned geom value(s) are not the planned point', bad;",
        "% row(s) do not hold the new point', bad;",
    ):
        assert f"RAISE EXCEPTION '{P.LABEL}: {says}" in sql, says
    rehearsal = P.render(rows, reversal=False, rehearsal=True)
    assert "\nROLLBACK;" in rehearsal and "COMMIT;" not in rehearsal


def test_the_undo_swaps_old_and_new_under_its_own_stamp() -> None:
    rows = P.changes([_move()])
    undo = P.render(rows, reversal=True)
    lat = next(r for r in rows if r.column == "lat")
    assert f"'lat', '{lat.new_value}', '{lat.old_value}', '{lat.change_key}-rollback'" in undo
    assert f"'{P.ROLLBACK_STAMP}'" in undo and f"'{P.RUN_STAMP}'" not in undo


class FakeDatabase:
    """A psql reader over three planned columns: it answers only the ids the SQL names."""

    def __init__(self, rows: list[P.Change], *, state: str, journal: bool) -> None:
        self.rows, self.state, self.journal = rows, state, journal

    def __call__(self, sql: str) -> list[dict[str, Any]]:
        if "FROM remediation_change_log" in sql:
            assert f"run_stamp = '{P.RUN_STAMP}'" in sql
            return [{"change_key": r.change_key} for r in self.rows] if self.journal else []
        ids = re.findall(r"'([0-9a-f-]{36})'::uuid", sql)
        assert ids, "the read names no site"
        out = []
        for sid in ids:
            mine = {r.column: r for r in self.rows if r.site_id == sid}
            if not mine:
                continue
            pick = "old_value" if self.state == "old" else "new_value"
            out.append(
                {
                    "site_id": sid,
                    "lat": getattr(mine["lat"], pick),
                    "lon": getattr(mine["lon"], pick),
                    "geom": mine["geom"].old_value if self.state == "old" else "0101...",
                    "geom_is_point": True,
                }
            )
        return out


def _written_plan(tmp_path: Path) -> list[P.Change]:
    (tmp_path / "coords.jsonl").write_text(json.dumps(_move()) + "\n", encoding="utf-8")
    return P.write_files(tmp_path)


def test_check_and_verify_read_the_database_and_refuse_an_edited_statement(tmp_path: Path) -> None:
    rows = _written_plan(tmp_path)
    old = FakeDatabase(rows, state="old", journal=False)
    assert P.run_readonly("check", tmp_path, reader=old) == 0
    assert P.run_readonly("verify", tmp_path, reader=old) == 1
    assert (
        P.run_readonly("verify", tmp_path, reader=FakeDatabase(rows, state="new", journal=True))
        == 0
    )
    assert (
        P.run_readonly("verify", tmp_path, reader=FakeDatabase(rows, state="new", journal=False))
        == 1
    )
    apply_sql = tmp_path / P.PLAN_DIR / "APPLY.sql"
    text = apply_sql.read_text(encoding="utf-8")
    apply_sql.write_text(text.replace("IF moved <> expected", "IF moved < 0"), encoding="utf-8")
    with pytest.raises(P.PlanError, match="APPLY.sql is not the statement this plan renders"):
        P.run_readonly("check", tmp_path, reader=lambda sql: pytest.fail("read an edited plan"))


def test_a_plan_that_is_not_the_verdicts_plan_is_refused(tmp_path: Path) -> None:
    _written_plan(tmp_path)
    moved = {**_move(), "new": {"lat": 18.2, "lon": -89.8}}
    (tmp_path / "coords.jsonl").write_text(json.dumps(moved) + "\n", encoding="utf-8")
    with pytest.raises(P.PlanError, match="not the plan the verdicts render"):
        P.run_readonly("check", tmp_path, reader=lambda sql: pytest.fail("read a stale plan"))


def test_a_coordinate_is_written_as_text_that_parses_back_to_the_same_double() -> None:
    for value in (18.105, -89.81055555555555, 41.0, 1e-05):
        assert float(P.number(value)) == value
    with pytest.raises(P.PlanError):
        P.number(float("nan"))


# ── the research behind the external-id repair's second wave ─────────────────────────────────


def _candidate(qid: str, identity: str, distance: float | None, p31: list[str]) -> dict[str, Any]:
    return {"qid": qid, "identity": identity, "distance_m": distance, "p31": p31, "enwiki": None}


def _research(page: dict[str, Any], candidates: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "old_qid": "Q744099",
        "stored_point": [53.0861, -4.336],
        "enwiki_page": page,
        "candidates": candidates,
    }


def test_rule_a_never_takes_a_village_for_the_hillfort_it_is_named_after() -> None:
    page = {
        "title": "Dinas Dinlle",
        "wikibase_item": "Q3402467",
        "redirected": False,
        "missing": False,
        "lat": None,
        "lon": None,
    }
    record = _research(
        page,
        [
            _candidate("Q3402467", "N1", 18.7, ["village"]),
            _candidate("Q106711669", "N1", 428.9, ["hill", "summit"]),
            _candidate("Q20590514", "N1", 506.7, ["contour fort"]),
        ],
    )
    assert R.suggest(record) == {"rule": "B", "qid": "Q20590514", "title": None}


def test_rule_b_needs_exactly_one_name_match_within_the_gate() -> None:
    page = {"title": "X", "wikibase_item": None, "redirected": False, "missing": True}
    far = _research(page, [_candidate("Q1", "N1", 1131.0, ["promontory fort"])])
    assert R.suggest(far)["rule"] == "unresolved"
    two = _research(
        page, [_candidate("Q1", "N1", 10.0, ["cave"]), _candidate("Q2", "N2", 20.0, ["cave"])]
    )
    assert R.suggest(two) == {
        "rule": "unresolved",
        "qid": None,
        "title": None,
        "near_matches": ["Q1", "Q2"],
    }


def test_rule_a_proves_the_place_by_the_article_when_wikidata_points_elsewhere() -> None:
    page = {
        "title": "Battle at the Harzhorn",
        "wikibase_item": "Q555463",
        "redirected": False,
        "missing": False,
        "lat": 51.83313889,
        "lon": 10.06683333,
    }
    record = {
        **_research(page, [_candidate("Q555463", "N1", 2622.3, ["battle", "battlefield"])]),
        "old_qid": "Q2221906",
        "stored_point": [51.83311, 10.06685],
    }
    assert R.suggest(record)["rule"] == "A"
    record["enwiki_page"] = {**page, "lat": 51.9, "lon": 10.06683333}
    assert R.suggest(record)["rule"] == "unresolved"


HARZHORN_PAGE = {
    "title": "Battle at the Harzhorn",
    "wikibase_item": "Q555463",
    "redirected": False,
    "missing": False,
    "lat": 51.83313889,
    "lon": 10.06683333,
}


def _harzhorn(**page: Any) -> dict[str, Any]:
    return {
        **_research(
            {**HARZHORN_PAGE, **page}, [_candidate("Q555463", "N3", 2622.3, ["battlefield"])]
        ),
        "old_qid": "Q2221906",
        "stored_point": [51.83311, 10.06685],
    }


def test_rule_a_needs_the_exact_title_of_an_existing_article_of_another_item() -> None:
    """A redirect names another article (Pyramid of Neferhetepes -> Pyramid of Userkaf), a missing page
    names nothing, and the item already linked is no replacement."""
    assert R.suggest(_harzhorn())["rule"] == "A"
    assert R.suggest(_harzhorn(redirected=True))["rule"] == "unresolved"
    assert R.suggest(_harzhorn(missing=True))["rule"] == "unresolved"
    same = {**_harzhorn(), "old_qid": "Q555463"}
    assert R.suggest(same)["rule"] == "unresolved"


def test_rule_b_takes_neither_the_old_item_nor_a_partial_name_nor_a_wikimedia_page() -> None:
    page = {"title": "X", "wikibase_item": None, "redirected": False, "missing": True}
    old = _research(page, [_candidate("Q744099", "N1", 10.0, ["hillfort"])])
    assert R.suggest(old)["rule"] == "unresolved"
    partial = _research(page, [_candidate("Q1", "N3", 10.0, ["cave"])])
    assert R.suggest(partial)["rule"] == "unresolved"
    listing = _research(page, [_candidate("Q2", "N1", 10.0, ["Wikimedia list article"])])
    assert R.suggest(listing)["rule"] == "unresolved"
    assert not R.is_site_kind(_candidate("Q3", "N1", 1.0, ["Wikimedia disambiguation page"]))
    assert R.suggest(_research(page, [_candidate("Q4", "N2", 10.0, ["cave"])]))["qid"] == "Q4"


# ── the research behind the third wave: kept names on a suspect link ─────────────────────────


def _verdict(site_id: str, group: str, suspect: list[str], **extra: Any) -> dict[str, Any]:
    return {
        "site_id": site_id,
        "group": group,
        "link_suspect": suspect,
        "class": "N1",
        "qid": "Q1",
        "en_label": "Tarxien Temples",
        **extra,
    }


def test_wave_three_takes_the_kept_names_on_a_generic_or_shared_link_only() -> None:
    """Q1 or Q2 on a kept name is wave 3; far only (Q4) is a coordinate question, a wrong link was
    wave 2's, a changed record says so in `state`, and a review row is read, not researched."""
    verdicts = [
        _verdict("a", "keep", ["Q2"]),
        _verdict("b", "keep", ["Q1"]),
        _verdict("c", "keep", ["Q2", "Q4"]),
        _verdict("d", "keep", ["Q4"]),
        _verdict("e", "keep", []),
        _verdict("f", "keep", ["Q2"], state="link changed since the census: Q1 -> Q2"),
        _verdict("g", "review", ["Q2"]),
        _verdict("h", "wrong-link", []),
        _verdict("i", "wrong-link", [], state="link changed since the census: Q1 -> Q2"),
    ]
    assert [v["site_id"] for v in R.suspect_links(verdicts)] == ["a", "b", "c"]
    assert [v["site_id"] for v in R.wrong_links(verdicts)] == ["h"]


def _maltese(site_id: str, name: str, qid: str, point: tuple[float, float]) -> dict[str, Any]:
    about = f"{name}, a Neolithic temple complex."
    return _site(name, qid, point, id=site_id, country="Malta", description=about)


TARXIEN = {
    SITE: _maltese(SITE, "Templos de Tarxien", "Q1", (35.86935, 14.51242)),
    OTHER: _maltese(OTHER, "Tarxien Temples", "Q1", (35.86969, 14.51243)),
    THIRD: _maltese(THIRD, "Hal Saflieni", "Q2", (35.86925, 14.50694)),
}


def test_the_rows_sharing_an_item_are_the_other_rows_and_a_stale_link_is_refused() -> None:
    shared = R.sharers(TARXIEN, SITE, "Q1")
    assert [(s["site_id"], s["name"]) for s in shared] == [(OTHER, "Tarxien Temples")]
    assert shared[0]["distance_m"] == pytest.approx(37.8, abs=0.1)
    assert R.sharers(TARXIEN, THIRD, "Q2") == []
    # the verdict's item must be the export's: a link repaired since is not researched as if not
    with pytest.raises(inputs.InputError, match="links 'Q1' in the export, not Q9"):
        R.sharers(TARXIEN, SITE, "Q9")


def _page_missing(title: str) -> dict[str, Any]:
    return {"query": {"pages": [{"title": title, "missing": True}]}}


def _entity(label: str, lat: float, lon: float, p31: str) -> dict[str, Any]:
    return {
        "labels": {"en": {"language": "en", "value": label}},
        "claims": {
            "P625": [
                {
                    "rank": "normal",
                    "mainsnak": {
                        "datavalue": {
                            "value": {
                                "latitude": lat,
                                "longitude": lon,
                                "precision": 0.0001,
                                "globe": "http://www.wikidata.org/entity/Q2",
                            }
                        }
                    },
                }
            ],
            "P31": [{"rank": "normal", "mainsnak": {"datavalue": {"value": {"id": p31}}}}],
        },
    }


def test_a_suspect_record_carries_its_tests_the_rows_sharing_its_item_and_the_rules() -> None:
    """The same research and the same rules as wave 2, and the facts the suspicion rests on."""
    net = FakeNet(
        [
            _page_missing("Templos de Tarxien"),
            {"query": {"geosearch": [{"title": "Q1"}, {"title": "Q5"}]}},
            {"search": [{"id": "Q1"}]},
            {
                "entities": {
                    "Q1": _entity("Tarxien Temples", 35.8697, 14.5124, "Q839954"),
                    "Q5": _entity("Templos de Tarxien", 35.8694, 14.5125, "Q839954"),
                }
            },
            {"entities": {"Q839954": {"labels": {"en": {"value": "archaeological site"}}}}},
        ]
    )
    verdict = _verdict(SITE, "keep", ["Q2"], name="Templos de Tarxien")
    record = R.research_suspect(net, verdict, TARXIEN)
    assert record["link_suspect"] == ["Q2"]
    assert [s["site_id"] for s in record["shared_with"]] == [OTHER]
    assert (record["country"], record["description"]) == ("Malta", TARXIEN[SITE]["description"])
    assert record["suggestion"] == {"rule": "B", "qid": "Q5", "title": None}
    assert record["suggestion"] == R.suggest(record)


def _research_tree(tmp_path: Path) -> tuple[Path, Path]:
    cache, out = tmp_path / "cache", tmp_path / "out"
    inputs.write_cache(cache / inputs.EXPORT_FILE, TARXIEN, {"exported_at": "test"})
    out.mkdir()
    verdicts = [
        _verdict(SITE, "keep", ["Q2"]),
        _verdict(THIRD, "wrong-link", [], qid="Q2", en_label="Hal Saflieni"),
    ]
    (out / "names.jsonl").write_text(
        "".join(json.dumps(v) + "\n" for v in verdicts), encoding="utf-8"
    )
    return cache, out


def test_research_suspects_writes_its_own_record_and_leaves_wave_twos_alone(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from bcases import run as RUN

    cache, out = _research_tree(tmp_path)
    net = FakeNet(
        [_page_missing("Templos de Tarxien"), {"query": {"geosearch": []}}, {"search": []}]
    )

    class Scripted:
        def __init__(self, *, root: Path, workers: int) -> None:
            assert root == cache / "http" and workers == 1

        def __enter__(self) -> FakeNet:
            return net

        def __exit__(self, *exc: object) -> None:
            return None

    monkeypatch.setattr(RUN, "Fetcher", Scripted)
    assert RUN.research(cache, out, suspects=True) == {"A": 0, "B": 0, "unresolved": 1}
    assert not (out / RUN.RESEARCH_FILE).exists()
    [record] = inputs.read_jsonl(out / RUN.SUSPECTS_FILE)
    assert record["site_id"] == SITE and record["shared_with"][0]["site_id"] == OTHER
    assert not net.answers


def test_the_suspects_flag_reaches_the_research_and_belongs_to_it_alone(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from bcases import run as RUN

    asked: list[dict[str, Any]] = []
    monkeypatch.setattr(
        RUN, "research", lambda cache, out, **kw: asked.append(kw) or {"A": 0, "B": 0}
    )
    where = ["--cache", str(tmp_path), "--out", str(tmp_path)]
    assert RUN.main(["research", "--suspects", *where]) == 0
    assert RUN.main(["research", *where]) == 0
    assert asked == [{"suspects": True}, {"suspects": False}]
    with pytest.raises(SystemExit) as refused:
        RUN.main(["plan", "--suspects", *where])
    assert refused.value.code == 2


def test_the_delivered_suspect_research_is_wave_threes_selection_under_the_same_rules() -> None:
    verdicts = inputs.read_jsonl(OUT / "names.jsonl")
    records = inputs.read_jsonl(OUT / "qid_research_suspects.jsonl")
    assert [r["site_id"] for r in records] == [v["site_id"] for v in R.suspect_links(verdicts)]
    assert not {r["site_id"] for r in records} & {v["site_id"] for v in R.wrong_links(verdicts)}
    tests = Counter("+".join(r["link_suspect"]) for r in records)
    assert tests == {"Q2": 33, "Q1": 3, "Q1+Q2": 1, "Q2+Q4": 2}
    for record in records:
        assert record["suggestion"] == R.suggest(record), record["name"]
    assert Counter(r["suggestion"]["rule"] for r in records) == {"B": 4, "unresolved": 35}


# ── the delivered files ───────────────────────────────────────────────────────────────────────


def test_the_counts_returned_are_the_counts_written() -> None:
    """The re-classification compares `write_all`'s return value with `COUNTS.json`; a boolean key
    (the first version's `b2_state`) comes back from JSON as "true" and can never compare equal."""
    names = [{"class": "N1", "group": "keep", "link_suspect": ["Q4"]}]
    coords = [
        {"verdict": "move", "reason": "agree", "country_after_move": {"agrees": True}},
        {"verdict": "review", "reason": "one witness only (wikidata)"},
    ]
    b2 = [
        {"class": "c2", "state": "open"},
        {"class": "b", "state": "written since the census: 'X' -> 'Y'"},
    ]
    counts = C.summarise(names, coords, b2, [], [], [], [], [])
    assert json.loads(json.dumps(counts)) == counts
    assert counts["b2_state"] == {"open": 1, "written since the census": 1}
    assert counts["names_keep_link_suspect"] == {"Q4": 1, "any": 1}


def test_the_delivered_counts_are_the_measured_ones() -> None:
    counts = json.loads((OUT / "COUNTS.json").read_text(encoding="utf-8"))
    assert counts["names_by_group"] == {"keep": 508, "review": 46, "wrong-link": 77}
    assert counts["names_keep_link_suspect"] == {"Q1": 4, "Q2": 36, "Q4": 35, "any": 72}
    assert sum(counts["names"].values()) == 631
    assert sum(counts["b2"].values()) == 117 and counts["b2"]["b"] == 5
    # JSON-native keys: `write_all` returns exactly what it writes (the re-classification compares them)
    assert counts["b2_state"] == {"open": 91, "written since the census": 26}
    assert counts["pairs"]["DUP"] == 20
    assert counts["duplicates"] == {"losers": 19, "unresolved_groups": 0, "held_groups": 1}
    assert sum(counts["coords_k_285"].values()) == 285
    assert counts["coords_verdict"]["move"] == 9 and counts["moves_country_follow_up"] == 0
    assert counts["stacked"] == {"groups": 13, "sites": 36}


def test_the_duplicate_file_is_what_the_scope_lane_reads() -> None:
    lines = inputs.read_jsonl(OUT / "DUPLICATES.jsonl")
    assert len(lines) == 19
    losers = [line["loser_id"] for line in lines]
    survivors = {line["survivor_id"] for line in lines}
    assert len(set(losers)) == len(losers) and not set(losers) & survivors
    for line in lines:
        assert set(line) == {"loser_id", "survivor_id", "evidence"}
        assert all({"source", "quote", "url"} == set(e) for e in line["evidence"])
    held = inputs.read_jsonl(OUT / "DUPLICATES_HELD.jsonl")
    assert [h["names"] for h in held] == [["Banias", "Caesarea Philippi"]]
    assert not {line["loser_id"] for line in held[0]["lines"]} & set(losers)


def test_every_planned_move_has_two_witnesses_that_are_not_one() -> None:
    """The owner's rule, read back from the delivered verdicts: no planned move rests on a pair the
    rules call one witness - a rounded copy, one point, or an import."""
    moves = [v for v in inputs.read_jsonl(OUT / "coords.jsonl") if v["verdict"] == "move"]
    assert len(moves) == 9
    for v in moves:
        ws = {w["kind"]: w for w in v["witnesses"]}
        a, b = (
            C.Witness(
                k,
                ws[k]["lat"],
                ws[k]["lon"],
                ws[k]["url"],
                ws[k]["quote"],
                ws[k]["precision_m"],
                ws[k]["derived_from"],
                C.grid_of(ws[k]["lat"], ws[k]["lon"]),
            )
            for k in ("wikidata", "enwiki")
        )
        assert C.independent(a, b), v["name"]
        assert C.rounded_copy(a, b) is None and C._m(a, b) > C.SAME_POINT_M, v["name"]


def test_the_delivered_coordinate_plan_is_the_verdicts_plan() -> None:
    verdicts = inputs.read_jsonl(OUT / "coords.jsonl")
    rows = P.changes(verdicts)
    delivered = inputs.read_jsonl(OUT / P.PLAN_DIR / "PLAN.jsonl")
    assert [r.change_key for r in rows] == [d["change_key"] for d in delivered]
    for name in ("APPLY.sql", "ROLLBACK.sql"):
        on_disk = (OUT / P.PLAN_DIR / name).read_text(encoding="utf-8")
        assert on_disk == P.statements(rows)[name]


needs_caches = pytest.mark.skipif(
    not (inputs.CACHE / inputs.NAMES_FILE).exists()
    or not (DATA / "run_t01" / "findings.jsonl").exists(),
    reason=f"the gitignored caches are not here ({inputs.CACHE}, {DATA / 'run_t01'}); "
    "run `bcases/run.py export` and `collect` with the census data",
)


@needs_caches
def test_a_full_reclassification_reproduces_the_delivered_verdicts(tmp_path: Path) -> None:
    counts = C.write_all(DATA, inputs.CACHE, tmp_path)
    assert counts == json.loads((OUT / "COUNTS.json").read_text(encoding="utf-8"))
    for name in (
        "names",
        "coords",
        "b2",
        "dup_pairs",
        "stacked",
        "DUPLICATES",
        "DUPLICATES_HELD",
    ):
        assert inputs.read_jsonl(tmp_path / f"{name}.jsonl") == inputs.read_jsonl(
            OUT / f"{name}.jsonl"
        ), name
