"""The owner cases of HUMAN_ONLY section B, decided from data (`scripts/remediation/bcases/`).

Every class is pinned by a case taken from the real examples the remaining-work map names - Q309
"history" on Clare, Suffolk; Calakmul stored 907 km off; Petroglyph Beach, whose Wikidata and Wikipedia
points are one point; the Pergamon Altar and a museum object stored at its museum; Dooey's Cairn and
Ballymacaldrack, one tomb recorded twice. Each guard has a test that goes red without it, and the
mutation sweep (`scripts/remediation/phase3/mutation_sweep.py`, "bcases") removes them one by one.

Nothing here reads the network or production: the fetcher and the psql reader are fakes that refuse
what the real ones refuse. The versioned deliverables (`output/remediation/bcases/`) are checked for
their shape and their pinned counts; the full re-classification needs the gitignored caches and skips
with its reason without them.
"""

from __future__ import annotations

import json
import re
import sys
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


# ── the coordinate witnesses ──────────────────────────────────────────────────────────────────


def _w(kind: str, point: tuple[float, float], **kw: Any) -> C.Witness:
    return C.Witness(kind, point[0], point[1], f"https://example.org/{kind}", kind, **kw)


def test_calakmul_moves_to_the_item_where_wikidata_and_wikipedia_agree() -> None:
    ws = [_w("enwiki", CALAKMUL_EN), _w("wikidata", CALAKMUL_WD, precision_m=15.5)]
    verdict = C.weigh(CALAKMUL_STORED, ws)
    assert verdict["verdict"] == "move"
    assert verdict["to"].kind == "wikidata" and verdict["agreeing"] == ["wikidata", "enwiki"]
    assert 40 < verdict["agreement_m"] < 60


def test_petroglyph_beach_counts_once_because_both_points_are_one_point() -> None:
    ws = [_w("wikidata", JUNEAU, precision_m=0.1), _w("enwiki", JUNEAU)]
    assert not C.independent(*ws)
    verdict = C.weigh(WRANGELL, ws)
    assert verdict["verdict"] == "review"
    assert verdict["reason"].startswith("the two witnesses are one: the same point")


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
            "precision": 1e-06,
            "globe": "Q2",
            "references": {},
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


MUSEUM = (48.8611, 2.3358)
FIND = (27.63, 38.55)


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
    site = _site("X", kw.get("qid"), point, country=kw.get("now", stored))
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
    lines, unresolved = C.duplicate_groups(pairs, sites)
    assert unresolved == []
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
    lines, unresolved = C.duplicate_groups(pairs, sites)
    assert lines == [] and unresolved == [sorted([SITE, OTHER, THIRD])]


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


def test_the_statement_is_guarded_and_every_change_goes_through_the_primitive() -> None:
    rows = P.changes([_move()])
    sql = P.render(rows, reversal=False)
    assert sql.startswith("-- Generated by scripts/remediation/bcases/coord_plan.py")
    assert f"-- plan sha256 {P.plan_digest(rows)}" in sql
    assert sql.rstrip().count("COMMIT;") == 1 and "\nROLLBACK;" not in sql
    assert "SET LOCAL lock_timeout = '10s';" in sql
    assert "     WHERE u.id IS NULL OR u.source_id <> 'ancient_nerds';" in sql
    assert (
        "HAVING array_agg(column_name ORDER BY column_name) <> ARRAY['geom', 'lat', 'lon']" in sql
    )
    assert "u.lat IS DISTINCT FROM p.old_value::double precision" in sql
    assert "g.new_value::geometry IS DISTINCT FROM" in sql
    assert "moved := moved + apply_remediation_change(" in sql
    assert "'unified_sites', r.column_name, 'id', r.site_id::text," in sql
    assert f"'{P.TEST_ID}', '{P.RUN_STAMP}', r.change_key, 'two_source'" in sql
    assert "IF moved <> expected THEN" in sql
    assert "ST_SetSRID(ST_MakePoint(u.lon, u.lat), 4326));" in sql
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


# ── the delivered files ───────────────────────────────────────────────────────────────────────


def test_the_delivered_counts_are_the_measured_ones() -> None:
    counts = json.loads((OUT / "COUNTS.json").read_text(encoding="utf-8"))
    assert counts["names_by_group"] == {"keep": 508, "review": 46, "wrong-link": 77}
    assert sum(counts["names"].values()) == 631
    assert sum(counts["b2"].values()) == 117
    assert counts["pairs"]["DUP"] == 20 and counts["duplicates"]["losers"] == 20
    assert sum(counts["coords_k_285"].values()) == 285
    assert counts["stacked"] == {"groups": 13, "sites": 36}


def test_the_duplicate_file_is_what_the_scope_lane_reads() -> None:
    lines = inputs.read_jsonl(OUT / "DUPLICATES.jsonl")
    assert len(lines) == 20
    losers = [line["loser_id"] for line in lines]
    survivors = {line["survivor_id"] for line in lines}
    assert len(set(losers)) == len(losers) and not set(losers) & survivors
    for line in lines:
        assert set(line) == {"loser_id", "survivor_id", "evidence"}
        assert all({"source", "quote", "url"} == set(e) for e in line["evidence"])


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
