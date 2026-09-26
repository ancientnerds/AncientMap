"""WD1's deterministic field status (`scripts/remediation/fields/classify.py`).

Pure functions over given inputs: the P31 table's pin and shape, the item's identity, each field's
CONFIRMED / CONFLICT / MISSING rule and the flags, including the cases the stage-1 measurement of
2026-09-26 found wrong in production - a point on the nearest village, a source URL on the island's
article, a redirect into another article's section, a period bucket off, stacked placeholder points.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[2]
if str(REPO / "scripts" / "remediation") not in sys.path:
    sys.path.insert(0, str(REPO / "scripts" / "remediation"))

from fields import classify as C  # noqa: E402
from fields import harvest as H  # noqa: E402

SITE = "0025b0ba-fd74-4c08-96e3-acc17956aa44"
TABLE = C.load_table()


def claim(prop: str, value: Any, rank: str = "normal", qualifiers: Any = None) -> dict[str, Any]:
    statement = {"rank": rank, "mainsnak": {"property": prop, "datavalue": {"value": value}}}
    if qualifiers:
        statement["qualifiers"] = qualifiers
    return statement


def entity(
    p31: tuple[str, ...] = ("Q44539",),
    point: tuple[float, float] | None = (37.9715, 23.7267),
    precision: float = 0.0001,
    dates: tuple[tuple[str, str, int], ...] = (),
    sitelinks: dict[str, str] | None = None,
) -> dict[str, Any]:
    claims: dict[str, list[Any]] = {"P31": [claim("P31", {"id": q}) for q in p31]}
    if point is not None:
        claims["P625"] = [
            claim("P625", {"latitude": point[0], "longitude": point[1], "precision": precision,
                           "globe": "http://www.wikidata.org/entity/Q2"})
        ]  # fmt: skip
    for prop, time, prec in dates:
        claims.setdefault(prop, []).append(claim(prop, {"time": time, "precision": prec}))
    return {
        "id": "Q1",
        "claims": claims,
        "sitelinks": {k: {"title": v} for k, v in (sitelinks or {"enwiki": "Parthenon"}).items()},
    }


def entries(*qids: str) -> list[C.ClassEntry]:
    return [TABLE[q] for q in qids]


NO_DOUBT = C.Identity(False, ())


class TestTheTable:
    def test_the_table_is_the_pinned_one_and_every_type_is_canonical(self) -> None:
        assert C.table_sha256() == C.TABLE_SHA256
        assert len(TABLE) == 766
        assert TABLE["Q839954"].kind == "generic"
        assert TABLE["Q486972"].kind == "container"
        assert TABLE["Q5"].kind == "other" and TABLE["Q5"].types == ()

    def test_a_changed_table_is_refused_until_the_pin_moves(self, tmp_path: Path) -> None:
        path = tmp_path / "t.json"
        path.write_bytes(C.TABLE.read_bytes() + b" ")
        with pytest.raises(C.TableError, match="not the pinned table"):
            C.load_table(path)

    @pytest.mark.parametrize(
        ("row", "message"),
        [
            ({"label": "x", "kind": "site", "types": ["Pagoda"]}, "not a canonical type"),
            ({"label": "x", "kind": "site", "types": ["temple"]}, "not a canonical type"),
            ({"label": "x", "kind": "maybe", "types": []}, "is not a table row"),
            ({"label": "x", "kind": "site"}, "is not a table row"),
            ({"label": "x", "kind": "site", "types": ["Temple", "Temple"]}, "listed twice"),
        ],
    )
    def test_a_malformed_row_is_refused(self, row: dict[str, Any], message: str) -> None:
        with pytest.raises(C.TableError, match=message):
            C.parse_table(json.dumps({"classes": {"Q1": row}}))

    def test_a_class_the_table_lacks_is_listed_by_how_often_it_is_named(self) -> None:
        missing = C.unmapped_classes(
            {"Q10": ["Q839954", "Q999999999"], "Q11": ["Q999999999"]}, TABLE
        )
        assert missing == {"Q999999999": 2}


class TestIdentity:
    def test_a_container_that_holds_no_stored_type_puts_the_item_in_doubt(self) -> None:
        assert C.identity("Temple", entries("Q23442")).doubt  # island
        assert C.identity("Fort", entries("Q54050")).doubt  # hill
        assert not C.identity("Fort", entries("Q54050", "Q744099")).doubt  # hill + hillfort
        assert not C.identity("Village", entries("Q532")).doubt
        assert C.identity("Tomb", entries("Q5")).doubt  # a person

    def test_no_container_no_doubt(self) -> None:
        assert not C.identity("Temple", entries("Q839954")).doubt


class TestCoordinates:
    STORED = (37.9715, 23.7267)

    def test_within_both_witnesses_is_confirmed(self) -> None:
        article = {"lat": 37.9716, "lon": 23.7266, "globe": "earth"}
        status = C.classify_coordinates(self.STORED, entity(), article, NO_DOUBT, 0)
        assert status.status == C.CONFIRMED
        assert len(status.evidence["witnesses"]) == 2

    def test_a_point_on_the_nearest_village_is_a_conflict(self) -> None:
        status = C.classify_coordinates(
            self.STORED, entity(point=(37.99, 23.75)), None, NO_DOUBT, 0
        )
        assert status.status == C.CONFLICT and "km from wikidata P625" in status.reason

    def test_a_coarse_p625_widens_its_own_tolerance(self) -> None:
        coarse = entity(point=(37.99, 23.75), precision=0.1)
        assert C.classify_coordinates(self.STORED, coarse, None, NO_DOUBT, 0).status == C.CONFIRMED

    def test_two_witnesses_that_disagree_are_a_conflict(self) -> None:
        # each within 1 km of the stored point, 1.7 km from each other
        article = {"lat": 37.9715, "lon": 23.7362, "globe": "earth"}
        west = entity(point=(37.9715, 23.7172))
        status = C.classify_coordinates(self.STORED, west, article, NO_DOUBT, 0)
        assert status.status == C.CONFLICT and "disagree" in status.reason

    def test_no_witness_is_missing_and_another_globe_is_no_witness(self) -> None:
        assert C.classify_coordinates(self.STORED, None, None, NO_DOUBT, 0).status == C.MISSING
        mars = {"lat": 37.9715, "lon": 23.7267, "globe": "mars"}
        assert (
            C.classify_coordinates(self.STORED, entity(point=None), mars, NO_DOUBT, 0).status
            == C.MISSING
        )

    def test_identity_doubt_is_a_conflict_whatever_the_distance(self) -> None:
        who = C.Identity(True, ("island",))
        status = C.classify_coordinates(self.STORED, entity(), None, who, 0)
        assert status.status == C.CONFLICT and status.reason.startswith("identity")

    def test_a_stacked_point_is_a_conflict_whatever_the_witnesses(self) -> None:
        # the Kilmartin Glen cairns share one placeholder point: a witness beside it proves nothing
        status = C.classify_coordinates(self.STORED, entity(), None, NO_DOUBT, 4)
        assert status.status == C.CONFLICT and status.reason.startswith("stacked: 4 other")
        assert status.evidence["stacked"] == 4


class TestPeriod:
    def test_a_year_span_follows_the_precision(self) -> None:
        assert C.year_span({"time": "-0447-00-00T00:00:00Z", "precision": 9}) == (-447, -447)
        assert C.year_span({"time": "+1500-00-00T00:00:00Z", "precision": 7}) == (1401, 1599)
        assert C.year_span({"time": "-3000-00-00T00:00:00Z", "precision": 6}) == (-3999, -2001)
        assert C.year_span({"time": "-10000-00-00T00:00:00Z", "precision": 5}) is None

    def test_the_earliest_start_decides_against_the_stored_bucket(self) -> None:
        dated = entity(
            dates=(("P571", "-0447-00-00T00:00:00Z", 9), ("P580", "-0600-00-00T00:00:00Z", 9))
        )
        status = C.classify_period(-447, dated, NO_DOUBT)
        assert status.status == C.CONFLICT  # P580 -600 lies in 1500 - 500 BC
        assert status.evidence["earliest"]["property"] == "P580"
        assert C.classify_period(-700, dated, NO_DOUBT).status == C.CONFIRMED

    def test_an_earliest_date_qualifier_is_read(self) -> None:
        qualified = entity()
        qualified["claims"]["P571"] = [
            claim("P571", {"time": "-0400-00-00T00:00:00Z", "precision": 9},
                  qualifiers={"P1319": [{"datavalue": {"value": {"time": "-2600-00-00T00:00:00Z",
                                                                 "precision": 9}}}]})
        ]  # fmt: skip
        status = C.classify_period(-2500, qualified, NO_DOUBT)
        assert (
            status.status == C.CONFIRMED and status.evidence["earliest"]["property"] == "P571/P1319"
        )

    def test_a_span_across_the_stored_bucket_is_inconclusive(self) -> None:
        century = entity(dates=(("P571", "-0500-00-00T00:00:00Z", 7),))
        assert C.classify_period(-450, century, NO_DOUBT).status == C.MISSING
        assert C.classify_period(100, century, NO_DOUBT).status == C.CONFLICT

    def test_no_date_is_missing_and_an_empty_field_is_asked_too(self) -> None:
        assert C.classify_period(-2500, entity(), NO_DOUBT).status == C.MISSING
        empty = C.classify_period(None, entity(), NO_DOUBT)
        assert empty.status == C.MISSING and empty.reason.startswith("empty")
        dated = entity(dates=(("P571", "-0447-00-00T00:00:00Z", 9),))
        assert C.classify_period(None, dated, NO_DOUBT).status == C.CONFLICT

    def test_a_date_from_1500_on_is_the_park_s_not_the_site_s(self) -> None:
        # Paphos Archaeological Park: P571 1962 is when the park was made
        park = entity(
            dates=(("P571", "+1962-00-00T00:00:00Z", 9), ("P571", "+1499-00-00T00:00:00Z", 9))
        )
        status = C.classify_period(-500, park, NO_DOUBT)
        assert [d["time"][:5] for d in status.evidence["modern"]] == ["+1962"]
        assert [d["time"][:5] for d in status.evidence["dates"]] == ["+1499"]
        only_modern = C.classify_period(
            -500, entity(dates=(("P571", "+1962-00-00T00:00:00Z", 9),)), NO_DOUBT
        )
        assert only_modern.status == C.MISSING and only_modern.reason == "no dated start"

    def test_a_doubted_item_s_dates_are_not_read(self) -> None:
        town = entity(dates=(("P571", "+1200-00-00T00:00:00Z", 9),))
        status = C.classify_period(-500, town, C.Identity(True, ("town",)))
        assert status.status == C.MISSING and status.evidence["dates"] == []


class TestSiteType:
    def test_a_specific_class_confirms_its_types(self) -> None:
        assert C.classify_site_type("Temple", entries("Q44539"), NO_DOUBT).status == C.CONFIRMED

    def test_a_generic_type_beside_a_specific_class_is_a_downgrade(self) -> None:
        status = C.classify_site_type(
            "Archaeological site", entries("Q839954", "Q15661340"), NO_DOUBT
        )
        assert status.status == C.CONFLICT and "ancient city" in status.reason

    def test_generic_classes_confirm_only_generic_types(self) -> None:
        assert (
            C.classify_site_type("Archaeological site", entries("Q839954"), NO_DOUBT).status
            == C.CONFIRMED
        )
        assert C.classify_site_type("Temple", entries("Q839954"), NO_DOUBT).status == C.MISSING

    def test_an_empty_type_is_asked_for(self) -> None:
        status = C.classify_site_type(None, entries("Q839954"), NO_DOUBT)
        assert status.status == C.MISSING and status.reason.startswith("empty")

    def test_no_item_or_no_class_is_missing(self) -> None:
        assert C.classify_site_type("Temple", None, NO_DOUBT).reason == "no item"
        assert C.classify_site_type("Temple", [], NO_DOUBT).reason == "the item has no class"

    def test_doubt_is_a_conflict(self) -> None:
        status = C.classify_site_type(
            "Fort", entries("Q54050"), C.identity("Fort", entries("Q54050"))
        )
        assert status.status == C.CONFLICT and status.reason.startswith("identity")


class TestSourceUrl:
    SITE_ROW = {"name": "Temple of Hephaestus", "qid": "Q1"}

    def record(self, **over: Any) -> dict[str, Any]:
        base = {
            "site_id": SITE,
            "source_url": "https://en.wikipedia.org/wiki/Temple_of_Hephaestus",
            "kind": H.URL_WIKIPEDIA,
            "lang": "en",
            "title": "Temple of Hephaestus",
            "resolved_title": "Temple of Hephaestus",
            "redirected": False,
            "fragment": None,
            "missing": False,
            "invalid": False,
            "wikibase_item": "Q1",
            "disambiguation": False,
        }
        base.update(over)
        return base

    def status(
        self, record: dict[str, Any], item: Any = None, who: C.Identity = NO_DOUBT
    ) -> C.Status:
        item = item or entity(sitelinks={"enwiki": "Temple of Hephaestus"})
        return C.classify_source_url(self.SITE_ROW, record, item, who)

    def test_the_item_s_own_article_is_confirmed(self) -> None:
        assert self.status(self.record()).status == C.CONFIRMED

    @pytest.mark.parametrize(
        ("over", "reason"),
        [
            ({"missing": True}, "dead"),
            ({"disambiguation": True}, "disambiguation"),
            ({"redirected": True, "fragment": "Tombs", "resolved_title": "Persepolis"}, "section"),
            ({"wikibase_item": "Q2"}, "another item's article"),
            ({"redirected": True, "resolved_title": "Stoa of Attalos"}, "another article"),
        ],
    )
    def test_what_makes_an_article_a_conflict(self, over: dict[str, Any], reason: str) -> None:
        status = self.status(self.record(**over))
        assert status.status == C.CONFLICT and reason in status.reason

    def test_a_benign_redirect_on_the_site_s_own_name_is_confirmed(self) -> None:
        benign = self.record(redirected=True, resolved_title="Hephaestus Temple")
        assert self.status(benign).status == C.CONFIRMED

    def test_the_island_s_article_is_a_conflict(self) -> None:
        status = self.status(self.record(), who=C.Identity(True, ("island",)))
        assert status.status == C.CONFLICT and "island" in status.reason

    @pytest.mark.parametrize(
        ("page", "expected"),
        [
            ({"status": 404, "final_url": "https://a.example/x"}, C.CONFLICT),
            ({"status": 403, "final_url": "https://a.example/x"}, C.MISSING),
            ({"status": None, "error": "ConnectError"}, C.MISSING),
            (
                {"status": 200, "final_url": "https://a.example/other", "page_title": "Hephaestus"},
                C.CONFLICT,
            ),
            (
                {
                    "status": 200,
                    "final_url": "https://www.a.example/x/",
                    "page_title": "Temple of Hephaestus",
                },
                C.CONFIRMED,
            ),
            (
                {"status": 200, "final_url": "https://a.example/x", "page_title": "Welcome"},
                C.MISSING,
            ),
        ],
    )
    def test_another_page_by_its_status_its_redirect_and_its_title(
        self, page: dict[str, Any], expected: str
    ) -> None:
        record = {"site_id": SITE, "source_url": "http://a.example/x", "kind": H.URL_WEB, **page}
        assert self.status(record).status == expected

    def test_no_url_is_asked_for_and_a_search_url_is_a_conflict(self) -> None:
        # HUMAN_ONLY_DECISIONS B3: an empty source_url gets a sourced URL of the site, or stays empty
        none = {"site_id": SITE, "source_url": None, "kind": H.URL_NONE}
        assert self.status(none).status == C.MISSING and self.status(none).reason.startswith(
            "empty"
        )
        search = {"site_id": SITE, "source_url": "https://google.com/x", "kind": H.URL_NOT_A_SOURCE}
        assert self.status(search).status == C.CONFLICT


class TestTheRun:
    def write_harvest(self, root: Path, **site_over: Any) -> None:
        site = {"site_id": SITE, "name": "Temple of Hephaestus", "country": "Greece",
                "lat": 37.9755, "lon": 23.7215, "qid": "Q1", "enwiki_title": "Temple of Hephaestus",
                "source_url": "https://en.wikipedia.org/wiki/Temple_of_Hephaestus", **site_over}  # fmt: skip
        root.mkdir(parents=True, exist_ok=True)
        (root / H.SITES_FILE).write_text(json.dumps(site) + "\n", encoding="utf-8")
        H._write_json(H.entity_path(root, "Q1"), entity(point=(37.9755, 23.7215),
                                                        sitelinks={"enwiki": "Temple of Hephaestus"}))  # fmt: skip
        H._write_json(root / H.CLASSES_FILE, {"Q44539": {"label": "temple", "p279": []}})
        H._write_json(H.url_path(root, SITE), TestSourceUrl().record())

    def stored(self, out: Path, *others: dict[str, Any], seeds: str = "", **over: Any) -> None:
        row = {"site_id": SITE, "name": "Temple of Hephaestus", "lat_text": "37.9755",
               "lon_text": "23.7215", "period_start": -449, "period_end": None,
               "period_name": "500 BC - 1 AD", "site_type": "Temple",
               "source_url": "https://en.wikipedia.org/wiki/Temple_of_Hephaestus",
               "scope_status": None, **over}  # fmt: skip
        out.mkdir(parents=True, exist_ok=True)
        rows = [row, *({**row, **other} for other in others)]
        text = "".join(json.dumps(r) + "\n" for r in rows)
        (out / C.STORED_FILE).write_text(text, encoding="utf-8")
        (out / C.SEEDS_FILE).write_text(seeds, encoding="utf-8")

    def seed(self, field: str, finding: str = "judged WRONG: the temple is on the Agora") -> str:
        seed = {"site_id": SITE, "field": field, "source": "stage 1", "finding": finding}
        return json.dumps(seed) + "\n"

    def test_a_site_is_classified_and_counted(self, tmp_path: Path) -> None:
        self.write_harvest(tmp_path / "h")
        self.stored(tmp_path / "o")
        counts = C.classify_all(tmp_path / "h", tmp_path / "o", table=TABLE, part="all")
        line = json.loads((tmp_path / "o" / C.CLASSIFIED_FILE).read_text(encoding="utf-8"))
        assert line["asked"] == ["period_start"]
        assert line["enwiki"] == "Temple of Hephaestus"
        assert counts["per_field"]["coordinates"] == {"CONFIRMED": 1}
        assert counts["sites_asked"] == 1

    def test_a_retired_site_is_not_classified(self, tmp_path: Path) -> None:
        self.write_harvest(tmp_path / "h")
        self.stored(tmp_path / "o", scope_status="retired")
        counts = C.classify_all(tmp_path / "h", tmp_path / "o", table=TABLE, part="all")
        assert counts["sites"] == 0 and counts["retired_not_classified"] == 1

    def test_a_harvest_and_an_export_of_different_states_are_refused(self, tmp_path: Path) -> None:
        self.write_harvest(tmp_path / "h")
        self.stored(tmp_path / "o", lat_text="37.0")
        with pytest.raises(C.ClassifyError, match="disagree on its point or URL"):
            C.classify_all(tmp_path / "h", tmp_path / "o", table=TABLE, part="all")

    def test_a_flag_asks_a_field_the_machine_confirms(self, tmp_path: Path) -> None:
        self.write_harvest(tmp_path / "h")
        seeds = self.seed("coordinates") + self.seed("coordinates", "again")
        self.stored(tmp_path / "o", seeds=seeds)
        counts = C.classify_all(tmp_path / "h", tmp_path / "o", table=TABLE, part="all")
        line = json.loads((tmp_path / "o" / C.CLASSIFIED_FILE).read_text(encoding="utf-8"))
        assert line["asked"] == ["coordinates", "period_start"]
        assert line["fields"]["coordinates"]["status"] == C.CONFIRMED
        assert line["fields"]["coordinates"]["flags"] == [
            "stage 1: judged WRONG: the temple is on the Agora",
            "stage 1: again",
        ]
        assert counts["flagged_only"]["coordinates"] == 1
        assert counts["seeds"] == {"sites": 1, "cells": 1, "sites_not_classified": []}

    def test_the_two_parts_split_the_sites_by_conflict_or_flag(self, tmp_path: Path) -> None:
        # the temple's only asked field is a MISSING start: it belongs to the rest; a flag on its
        # confirmed point moves it to the conflict part
        self.write_harvest(tmp_path / "h")
        self.stored(tmp_path / "o")
        assert (
            C.classify_all(tmp_path / "h", tmp_path / "o", table=TABLE, part="rest")["sites"] == 1
        )
        conflict = C.classify_all(tmp_path / "h", tmp_path / "o", table=TABLE, part="conflict")
        assert conflict["sites"] == 0 and conflict["part"] == "conflict"
        self.stored(tmp_path / "o", seeds=self.seed("coordinates"))
        assert (
            C.classify_all(tmp_path / "h", tmp_path / "o", table=TABLE, part="conflict")["sites"]
            == 1
        )
        assert (
            C.classify_all(tmp_path / "h", tmp_path / "o", table=TABLE, part="rest")["sites"] == 0
        )
        with pytest.raises(C.ClassifyError, match="is not one of"):
            C.classify_all(tmp_path / "h", tmp_path / "o", table=TABLE, part="some")

    def test_the_seeds_must_be_there_and_well_formed(self, tmp_path: Path) -> None:
        self.write_harvest(tmp_path / "h")
        self.stored(tmp_path / "o")
        (tmp_path / "o" / C.SEEDS_FILE).unlink()
        with pytest.raises(C.ClassifyError, match="seeds.py build"):
            C.classify_all(tmp_path / "h", tmp_path / "o", table=TABLE, part="all")
        for bad in (
            self.seed("period_name"),
            self.seed("site_type", " "),
            json.dumps({"site_id": SITE, "field": "site_type"}) + "\n",
        ):
            self.stored(tmp_path / "o", seeds=bad)
            with pytest.raises(C.ClassifyError, match="is not a seed|no finding"):
                C.classify_all(tmp_path / "h", tmp_path / "o", table=TABLE, part="all")

    def test_a_point_another_live_site_holds_is_stacked(self, tmp_path: Path) -> None:
        self.write_harvest(tmp_path / "h")
        twin = {"site_id": "99a98235-0000-4000-8000-000000000001", "name": "Stoa"}
        gone = {"site_id": "99a98235-0000-4000-8000-000000000002", "scope_status": "retired"}
        self.stored(tmp_path / "o", twin, gone)
        counts = C.classify_all(tmp_path / "h", tmp_path / "o", table=TABLE, part="all")
        line = json.loads((tmp_path / "o" / C.CLASSIFIED_FILE).read_text(encoding="utf-8"))
        assert line["fields"]["coordinates"]["evidence"]["stacked"] == 1  # the retired one not
        assert "coordinates" in line["asked"] and counts["stacked_points"] == 1

    def test_a_source_url_record_of_another_url_is_refused(self, tmp_path: Path) -> None:
        self.write_harvest(tmp_path / "h")
        self.stored(tmp_path / "o")
        stale = {**TestSourceUrl().record(), "source_url": "https://en.wikipedia.org/wiki/Theseion"}
        H._write_json(H.url_path(tmp_path / "h", SITE), stale)
        with pytest.raises(H.HarvestError, match="run `harvest.py fetch` again"):
            C.classify_all(tmp_path / "h", tmp_path / "o", table=TABLE, part="all")

    def test_a_class_the_table_lacks_stops_the_classification(self, tmp_path: Path) -> None:
        self.write_harvest(tmp_path / "h")
        self.stored(tmp_path / "o")
        partial = {q: e for q, e in TABLE.items() if q != "Q44539"}
        with pytest.raises(C.TableError, match="Q44539 'temple' x1"):
            C.classify_all(tmp_path / "h", tmp_path / "o", table=partial, part="all")

    def test_names_it_reads_a_distinctive_word_folded(self) -> None:
        assert C.names_it("Tempio di Ercole", "Il tempio di ERCOLE")
        assert C.names_it("Nea Paphos", "Paphos Archaeological Park")
        assert not C.names_it("Temple of Apollo", "a temple")
        assert not C.names_it("Temple of Apollo", None)
