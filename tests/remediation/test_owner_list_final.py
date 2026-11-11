"""The final owner list (`scripts/remediation/owner_list_final.py`, MASTER_PLAN Phase 8).

DB-less: production is a fixture export, the field runs are stand-in build results (the real
`fields/owner_list.build` is tested in `test_fields_wd3.py` / `test_fields_wd5.py`), the lane lists
files in a temporary `output/remediation`. Each rule is asserted by the row it keeps or sets aside
(`mechanical/mutation_sweep.py "d25-owner:"`).
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

import owner_list_final as F  # noqa: E402
from mechanical.plan import SNAPSHOT_KIND  # noqa: E402

SITE = "0025b0ba-fd74-4c08-96e3-acc17956aa44"
OTHER = "786cada5-1feb-4c5c-9e79-b8ffdf8aacc6"
THIRD = "9fe8d7e0-6fa4-4ab3-86b5-b33f0a95fd86"
HERO = {"filename": "Kourion.jpg", "width": 2400, "height": 1600, "license": "CC BY-SA 4.0",
        "author": "A. Author", "license_url": "https://creativecommons.org/licenses/by-sa/4.0/"}  # fmt: skip


#: Another live row of at least 1600x900: the swap D48 asks the owner about.
LARGER: dict[str, Any] = {
    "hero_larger": {"id": 58086, "filename": "Big.webp", "width": 1600, "height": 2440},
    "hero_larger_rows": 3,
}
#: The site_type merge's map as `build` passes it (alias -> target).
MERGES = {
    "Settlement": "City/town/settlement",
    "Urban": "City/town/settlement",
    "Fortress": "Fortress/citadel",
}


def site(site_id: str = SITE, **over: Any) -> dict[str, Any]:
    """A shown curated site with nothing open."""
    base: dict[str, Any] = {
        "site_id": site_id,
        "name": "Kourion",
        "country": "Cyprus",
        "scope_status": None,
        "site_type": "City/town/settlement",
        "period_start": -1200,
        "period_name": "1500 - 500 BC",
        "lat": "34.664",
        "lon": "32.887",
        "source_url": "https://en.wikipedia.org/wiki/Kourion",
        "thumbnail_url": "/data/images/k.webp",
        "no_description": False,
        "description_start": "Kourion was a city on the south coast of Cyprus.",
        "card_description": "A card.",
        "card_contract": "shorts-v1",
        "coord_kind": "quote",
        "period_kind": "two_source",
        "images": 4,
        "hero": dict(HERO),
        "hero_larger": None,
        "hero_larger_rows": 0,
        "has_qid": True,
        "card_qid": None,
        "card_wiki_url": None,
        "qid": "Q1",
        "enwiki_title": "Kourion",
    }
    base.update(over)
    return base


def topics(rows: list[dict[str, Any]]) -> dict[str, str]:
    return {r["topic"]: r["reason"] for r in rows}


class TestProduction:
    def test_a_site_with_nothing_open_is_not_listed(self) -> None:
        assert F.production_rows([site()]) == []

    @pytest.mark.parametrize(
        ("over", "topic"),
        [
            ({"no_description": True}, "description-empty"),
            ({"card_description": None}, "card-empty"),
            ({"card_contract": ""}, "card-old-kept"),
            ({"thumbnail_url": None, "images": 0, "hero": None}, "image-none"),
            ({"images": 0, "hero": None}, "image-thumbnail-only"),
            ({"hero": {**HERO, "width": 800}, **LARGER}, "hero-small"),
            ({"hero": {**HERO, "height": 600}, **LARGER}, "hero-small"),
            ({"hero": {**HERO, "width": None}}, "hero-size-unknown"),
            ({"hero": {**HERO, "author": " "}}, "hero-credit-missing"),
            ({"hero": {**HERO, "license_url": None}}, "hero-credit-missing"),
            ({"site_type": None}, "site-type-empty"),
            ({"period_start": None, "period_name": "Undated"}, "period-undated"),
            ({"period_kind": "derived"}, "period-rule-made"),
            ({"period_kind": "band"}, "period-rule-made"),
            ({"period_kind": None}, "period-unmarked"),
            ({"coord_kind": "unsourced"}, "point-unsourced"),
            ({"coord_kind": None}, "point-unmarked"),
            ({"source_url": ""}, "source-url-empty"),
            ({"has_qid": False}, "wikidata-id-none"),
            ({"scope_status": "pending"}, "scope-pending"),
            ({"card_qid": "Q2"}, "card-id-drift"),
            ({"card_qid": "Q1", "qid": None}, "card-id-drift"),
            ({"card_wiki_url": "https://en.wikipedia.org/wiki/Curium"}, "card-id-drift"),
        ],
    )
    def test_each_gap_is_its_own_topic(self, over: dict[str, Any], topic: str) -> None:
        rows = F.production_rows([site(**over)])
        assert topic in topics(rows)
        row = next(r for r in rows if r["topic"] == topic)
        assert row["source"] == "production" and row["decision"] == F.TOPIC_OF[topic].decision

    def test_a_card_holding_its_site_s_ids_has_no_drift(self) -> None:
        held = site(card_qid="Q1", card_wiki_url="https://en.wikipedia.org/wiki/Kourion")
        assert F.production_rows([held]) == []
        spaced = site(enwiki_title="Ancient Kourion",
                      card_wiki_url="https://en.wikipedia.org/wiki/Ancient_Kourion")  # fmt: skip
        assert F.production_rows([spaced]) == []

    def test_the_hero_sizes_count_the_swaps_d48_asks_about(self) -> None:
        sites = [
            site(),
            site(OTHER, hero={**HERO, "width": 800, "height": 600}, **LARGER),
            site(THIRD, hero={**HERO, "width": 1200, "height": 800}),
            site("4", hero={**HERO, "width": 640}, scope_status="retired", **LARGER),
            site("5", hero={**HERO, "width": None}, **LARGER),
            site("6", hero=None),
        ]
        assert F.hero_sizes(sites) == {"small": 2, "with_a_larger_row": 1, "without": 1}

    def test_a_small_hero_names_the_row_that_could_replace_it(self) -> None:
        rows = F.production_rows([site(hero={**HERO, "width": 800, "height": 600}, **LARGER)])
        assert topics(rows) == {
            "hero-small": "hero Kourion.jpg is 800x600; the largest other live row is 58086 "
            "Big.webp (1600x2440), one of 3 at least 1600x900"
        }

    def test_a_small_hero_without_a_larger_row_is_counted_not_listed(self) -> None:
        """D48 is the census's 433: a small hero whose site holds a larger live row. Without one
        there is nothing for the owner to swap."""
        assert F.production_rows([site(hero={**HERO, "width": 800, "height": 600})]) == []

    def test_a_large_hero_with_a_larger_row_is_not_small(self) -> None:
        assert F.production_rows([site(**LARGER)]) == []

    def test_an_empty_card_is_not_also_an_old_one(self) -> None:
        assert set(topics(F.production_rows([site(card_description="", card_contract="")]))) == {
            "card-empty"
        }

    def test_a_free_licence_asks_no_credit(self) -> None:
        free = {**HERO, "license": "Public domain", "author": None, "license_url": None}
        assert F.production_rows([site(hero=free)]) == []

    def test_a_hero_of_exactly_the_bound_is_not_small(self) -> None:
        exact = {**HERO, "width": F.HERO_WIDTH, "height": F.HERO_HEIGHT}
        assert F.production_rows([site(hero=exact, **LARGER)]) == []

    def test_a_retired_site_is_never_listed(self) -> None:
        assert F.production_rows([site(scope_status="retired", no_description=True)]) == []


def run_row(site_id: str = SITE, field: str = "period_start", **over: Any) -> dict[str, Any]:
    base = {"site_id": site_id, "name": "Kourion", "country": "Cyprus", "field": field,
            "state": "unresolved", "open_because": "rule-made", "stored": -1200,
            "reason": "no source states a start", "asked": 1}  # fmt: skip
    base.update(over)
    return base


def result(*rows: dict[str, Any]) -> dict[str, Any]:
    return {"rows": list(rows), "counts": {}, "population": {}}


class TestTheFieldRuns:
    def test_an_open_field_row_is_listed_with_its_run(self) -> None:
        rows, aside = F.field_rows(
            [("wd3", result(run_row()), {(SITE, "period_start")})], {SITE: site()}, MERGES
        )
        assert [(r["topic"], r["source"], r["state"]) for r in rows] == [
            ("field-period_start", "fields-wd3", "unresolved")
        ]
        assert "rule-made: no source states a start" == rows[0]["reason"] and not aside

    def test_the_last_run_that_asked_a_field_decides_it(self) -> None:
        """WD3 left the start unresolved; wd5 asked it again and kept it with a quote, so wd5
        lists nothing for it - and WD3's row is closed."""
        runs = [
            ("wd3", result(run_row()), {(SITE, "period_start")}),
            ("wd5", result(), {(SITE, "period_start")}),
        ]
        assert F.field_rows(runs, {SITE: site()}, MERGES) == ([], F.Counter())

    def test_a_later_run_that_did_not_ask_the_field_leaves_it_open(self) -> None:
        runs = [
            ("wd3", result(run_row()), {(SITE, "period_start")}),
            ("wd5", result(), {(SITE, "coordinates")}),
        ]
        rows, _aside = F.field_rows(runs, {SITE: site()}, MERGES)
        assert [r["source"] for r in rows] == ["fields-wd3"]

    def test_a_value_a_later_write_replaced_is_superseded(self) -> None:
        rows, aside = F.field_rows(
            [("wd3", result(run_row(stored=-2000)), {(SITE, "period_start")})],
            {SITE: site()},
            MERGES,
        )
        assert rows == [] and aside == {"superseded": 1}

    def test_a_point_is_compared_as_numbers(self) -> None:
        point = run_row(field="coordinates", stored="34.6640, 32.887")
        rows, _ = F.field_rows(
            [("wd5", result(point), {(SITE, "coordinates")})], {SITE: site()}, MERGES
        )
        assert [r["topic"] for r in rows] == ["field-coordinates"]
        moved = run_row(field="coordinates", stored="34.7, 32.887")
        assert F.field_rows(
            [("wd5", result(moved), {(SITE, "coordinates")})], {SITE: site()}, MERGES
        )[1] == {"superseded": 1}

    def test_a_site_type_the_merge_renamed_is_still_open(self) -> None:
        """The merge moves `Settlement` to `City/town/settlement` and answers nothing: the wd4
        question stays open. A type a later write changed to another type was answered."""
        asked = run_row(field="site_type", stored="Settlement", state="refused")
        rows, aside = F.field_rows(
            [("wd4", result(asked), {(SITE, "site_type")})], {SITE: site()}, MERGES
        )
        assert [(r["topic"], r["state"]) for r in rows] == [("field-site_type", "refused")]
        assert rows[0]["reason"].startswith(
            "(the site_type merge renamed 'Settlement' to 'City/town/settlement') "
        )
        assert not aside
        same = run_row(field="site_type", stored="City/town/settlement")
        rows, _ = F.field_rows(
            [("wd4", result(same), {(SITE, "site_type")})], {SITE: site()}, MERGES
        )
        assert rows[0]["reason"] == "rule-made: no source states a start"
        moved = run_row(field="site_type", stored="Fortress")
        assert F.field_rows(
            [("wd4", result(moved), {(SITE, "site_type")})], {SITE: site()}, MERGES
        ) == ([], {"superseded": 1})

    def test_a_type_moved_to_another_alias_of_its_target_was_a_write(self) -> None:
        """`Settlement` and `Urban` merge into one target, but the merge never writes one into the
        other: a row now holding `Urban` was written by a later lane, so the question was answered."""
        asked = run_row(field="site_type", stored="Settlement")
        assert F.field_rows(
            [("wd4", result(asked), {(SITE, "site_type")})], {SITE: site(site_type="Urban")}, MERGES
        ) == ([], {"superseded": 1})

    def test_a_retired_or_gone_site_is_set_aside(self) -> None:
        runs = [
            (
                "wd3",
                result(run_row(), run_row(OTHER)),
                {(SITE, "period_start"), (OTHER, "period_start")},
            )
        ]
        rows, aside = F.field_rows(runs, {SITE: site(scope_status="retired")}, MERGES)
        assert rows == [] and aside == {"retired-or-gone": 2}


class TestTheFieldRunFiles:
    """A field run's own owner files are no list of their own: its rows are rebuilt."""

    def test_every_owner_artefact_of_2026_11_10_has_its_source_or_its_reason(self) -> None:
        """The twelve artefacts `--final` refused on 2026-11-10 (code gap phase8-closeout#2), less
        the two hero-moves lists, which are the image lanes' own source."""
        runs = F.field_run_names(Path("nowhere"))
        assert runs == F.FIELD_RUNS and runs[-3:] == ("wd5r/pilot", "wd5r/pilot2", "d121/d124")
        for rel in (
            "fields/d121/d124/adv/OWNER.jsonl",
            "fields/wd5r/pilot/DECISIONS.pre-owner-1.jsonl",
            "fields/wd5r/pilot/adv/OWNER.jsonl",
            "fields/wd5r/pilot/adv/OWNER_REJECTED.jsonl",
            "fields/wd5r/pilot2/adv/OWNER.jsonl",
        ):
            assert F._of_a_field_run(rel, runs), rel
        for rel in (
            "fields/wd5x/OWNER_SHOWN.candidates.json",
            "fields/wd5x/report-615/OWNER_SCOPE.jsonl",
            "insert_site/d57-2026-11-05/D114_OWNER_ROUND.json",
            "insert_site/d57-2026-11-05/D130_OWNER_ROUND.json",
            "insert_site/d57-2026-11-05/D143_OWNER_ROUND.json",
        ):
            assert F.OUT_OF_SCOPE[rel].strip() and not F._of_a_field_run(rel, runs), rel
        assert "D1-D156" in F.OUT_OF_SCOPE["OWNER_DECISIONS_2026-10-08.md"]

    def test_a_file_deeper_in_a_run_or_of_a_run_of_a_similar_name_is_not_the_runs(self) -> None:
        runs = ("wd5", "wd5r/pilot")
        assert F._of_a_field_run("fields/wd5/OWNER_LIST.jsonl", runs)
        assert F._of_a_field_run("fields/wd5/adv/OWNER.jsonl", runs)
        assert not F._of_a_field_run("fields/wd5/write/2026-10-09a/OWNER.jsonl", runs)
        assert not F._of_a_field_run("fields/wd5-reask/adv/OWNER.jsonl", runs)
        assert not F._of_a_field_run("fields/wd5r/pilot2/adv/OWNER.jsonl", runs)
        assert not F._of_a_field_run("fields/wd5r/pilot/adv/x/OWNER.jsonl", runs)
        assert not F._of_a_field_run("served_image/wd5/OWNER.jsonl", runs)


SYBARIS_ON_THE_TRAEIS = "251ac618-a557-4c31-9129-65afc47b649d"
TICHIT = "1e5f61dd-b362-4985-b235-dadeea0eca0f"
QASR_QAROUN = "3ac3c796-1538-47b5-8985-6807adf8dec3"
POINT = {"lat": "39.716823473968", "lon": "16.493845981232198"}


def followup(site_id: str, **over: Any) -> dict[str, Any]:
    base = {"site_id": site_id, "name": "n", "lane": "fields coordinates (D19)",
            "issue": "the record carries another record's point", "found_by": "review"}  # fmt: skip
    return {**base, **over}


class TestTheFollowUps:
    """`CLOSEOUT_FOLLOWUPS.jsonl`: a follow-up is listed while production still shows its defect."""

    def rows(self, site_id: str, *sites: dict[str, Any]) -> tuple[list[dict[str, Any]], Any]:
        return F.followup_rows([followup(site_id)], {s["site_id"]: s for s in sites})

    def test_a_record_at_another_records_point_is_open_until_it_moves(self) -> None:
        sybaris = site(F.SYBARIS, name="Sybaris", **POINT)
        rows, closed = self.rows(
            SYBARIS_ON_THE_TRAEIS, site(SYBARIS_ON_THE_TRAEIS, **POINT), sybaris
        )
        assert [(r["topic"], r["source"], r["state"], r["decision"]) for r in rows] == [
            ("closeout-followup", "closeout-followups", "open", "D19")
        ]
        assert rows[0]["reason"] == (
            "its point 39.716823473968, 16.493845981232198 is still the point of Sybaris - "
            "fields coordinates (D19): the record carries another record's point"
        )
        assert closed == {}
        # the same point written with other digits is the same point
        same = site(SYBARIS_ON_THE_TRAEIS, lat="39.7168234739680", lon="16.493845981232198")
        assert len(self.rows(SYBARIS_ON_THE_TRAEIS, same, sybaris)[0]) == 1
        for moved in ({"lat": "39.5"}, {"lon": "16.75"}):
            rows, closed = self.rows(
                SYBARIS_ON_THE_TRAEIS, site(SYBARIS_ON_THE_TRAEIS, **{**POINT, **moved}), sybaris
            )
            assert rows == [] and closed == {
                SYBARIS_ON_THE_TRAEIS: "the record no longer shares the point of Sybaris"
            }

    def test_a_record_under_another_records_text_is_open_until_the_text_is_its_own(self) -> None:
        theirs = site(TICHIT, description_start="The Neolithic sites of Dhar Tichitt were settled")
        rows, _ = self.rows(TICHIT, theirs)
        assert rows[0]["reason"].startswith(
            "its description still begins 'The Neolithic sites of Dhar Tichitt' - "
        )
        assert rows[0]["decision"] == "D13/D20"
        for own in ("Tichit is a town in Mauritania.", None):
            assert self.rows(TICHIT, site(TICHIT, description_start=own)) == (
                [],
                {TICHIT: "the description is no longer Dhar Tichitt's"},
            )

    def test_a_record_without_a_hero_is_open_unless_image_none_lists_it(self) -> None:
        thumbnail_only = site(QASR_QAROUN, hero=None, images=0)
        rows, _ = self.rows(QASR_QAROUN, thumbnail_only)
        assert rows[0]["reason"].startswith(
            "it has no hero row and is not listed under `image-none` - "
        )
        assert rows[0]["decision"] == "D17/D82"
        how = {QASR_QAROUN: "a hero row exists, or `image-none` lists the site"}
        assert self.rows(QASR_QAROUN, site(QASR_QAROUN)) == ([], how)
        bare = site(QASR_QAROUN, hero=None, images=0, thumbnail_url=None)
        assert self.rows(QASR_QAROUN, bare) == ([], how)
        assert "image-none" in topics(F.production_rows([bare]))

    def test_a_follow_up_of_a_retired_or_gone_site_is_closed(self) -> None:
        retired = site(TICHIT, scope_status="retired",
                       description_start="The Neolithic sites of Dhar Tichitt")  # fmt: skip
        assert self.rows(TICHIT, retired) == ([], {TICHIT: "the site is retired or gone"})
        assert self.rows(TICHIT) == ([], {TICHIT: "the site is retired or gone"})

    def test_a_follow_up_without_a_check_stays_open_while_its_site_is_shown(self) -> None:
        assert SITE not in F.FOLLOWUP_CHECKS
        rows, closed = self.rows(SITE, site())
        assert closed == {} and rows[0]["decision"] == "-"
        assert rows[0]["reason"].startswith(F.FOLLOWUP_UNCHECKED + " - fields coordinates (D19): ")
        assert self.rows(SITE, site(scope_status="retired"))[0] == []

    def test_the_three_follow_ups_of_2026_10_24_have_their_checks(self) -> None:
        assert set(F.FOLLOWUP_CHECKS) == {SYBARIS_ON_THE_TRAEIS, TICHIT, QASR_QAROUN}
        assert F._title(F.FOLLOWUP_TOPIC) == (F.FOLLOWUP_TITLE, "D13/D20/D17/D82/D19")


class TestTheLaneLists:
    LANE = F.LANE_LISTS[0]

    def test_a_lane_row_carries_its_state_and_verdict(self) -> None:
        listed = [{"site_id": SITE, "name": "x", "state": "rejected", "verdict": "RETARGET",
                   "reason": "the ancient site has no item of its own"}]  # fmt: skip
        rows, aside = F.lane_rows(self.LANE, listed, {SITE: site()})
        assert rows[0]["topic"] == self.LANE.topic and rows[0]["state"] == "rejected"
        assert rows[0]["reason"] == "RETARGET: the ancient site has no item of its own"
        assert rows[0]["source"] == self.LANE.name and aside == 0

    def test_a_lane_row_of_a_retired_site_is_set_aside(self) -> None:
        listed = [{"site_id": SITE, "state": "held", "reason": "r"}]
        assert F.lane_rows(self.LANE, listed, {SITE: site(scope_status="retired")}) == ([], 1)

    def test_an_owner_list_no_source_covers_is_named(self, tmp_path: Path) -> None:
        for rel in (
            "fields/wd3/OWNER_LIST.jsonl",  # rebuilt from the run
            "fields/wd3/OWNER_LIST.md",  # its rendering
            "fields/wd5/adv/OWNER.jsonl",  # in the run's rows
            "fields/wd5/cache/x/OWNER.jsonl",  # a cache, never a list
            F.LANE_LISTS[0].path,  # registered
            F.LANE_LISTS[0].path.removesuffix(".jsonl") + ".md",  # its rendering
            "final-2026-10-08/OWNER_LIST_FINAL.md",  # this builder's own output
            "HUMAN_ONLY.md",  # out of scope, with its reason
            "teaser/runs/owner-d47-2026-10-19/OUTCOMES.jsonl",  # an out-of-scope directory
            "images/d17/OWNER_LIST.jsonl",  # nobody reads it
            "teaser/runs/owner-d99/OUTCOMES.jsonl",  # an owner run nobody registered
            "qid_repair/HUMAN_ONLY_LEFTOVERS.md",  # another name for an owner list
            "qid_repair/owner.sql",  # not a list's suffix
            "fields/wd5r/pilot/adv/OWNER.jsonl",  # a run one level deeper: in its rows
            "fields/wd5r/pilot/adv/OWNER_REJECTED.jsonl",  # the cells D112 did not write
            "fields/wd5r/pilot/DECISIONS.pre-owner-1.jsonl",  # the run's file before them
            "fields/d121/d124/adv/OWNER.jsonl",  # the D124 re-ask
            "fields/wd5r/pilot3/adv/OWNER.jsonl",  # a pilot nobody registered
            "fields/wd5r/OWNER_NOTES.md",  # beside the pilots, of no run
            "fields/wd5-point/2026-11-11/RUN.json",  # a listed-point run ...
            "fields/wd5-point/2026-11-11/adv/OWNER.jsonl",  # ... is found, its list in its rows
            "fields/wd5-point/2026-11-12/adv/OWNER.jsonl",  # a directory without a run
            "fields/wd5x/OWNER_SHOWN.candidates.json",  # out of scope: a sample of cells
            "fields/wd5x/report-615/OWNER_SCOPE.jsonl",  # out of scope: the failed extractor's
            "insert_site/d57-2026-11-05/D114_OWNER_ROUND.json",  # out of scope: a round's input
            "insert_site/d57-2026-11-05/D999_OWNER_ROUND.json",  # a round nobody registered
        ):
            (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
            (tmp_path / rel).write_text("", encoding="utf-8")
        found = F.unregistered_lists(tmp_path, [F.LANE_LISTS[0].path])
        assert found == [
            "fields/wd5-point/2026-11-12/adv/OWNER.jsonl",
            "fields/wd5r/OWNER_NOTES.md",
            "fields/wd5r/pilot3/adv/OWNER.jsonl",
            "images/d17/OWNER_LIST.jsonl",
            "insert_site/d57-2026-11-05/D999_OWNER_ROUND.json",
            "qid_repair/HUMAN_ONLY_LEFTOVERS.md",
            "teaser/runs/owner-d99",
        ]


class TestTheRunLists:
    """The image lanes' lists: each run writes its own, into its own dated run directory."""

    D17, D59, MOVES = F.RUN_LISTS
    BARE: dict[str, Any] = {"thumbnail_url": None, "images": 0, "hero": None}

    def test_a_research_row_is_the_reason_of_a_site_that_still_shows_no_picture(self) -> None:
        listed = [{"site_id": SITE, "reason": "the search found no Commons candidate (x)"}]
        rows, aside = F.run_list_rows(self.D17, "d17-s01", listed, {SITE: site(**self.BARE)})
        assert (rows[0]["topic"], rows[0]["source"], rows[0]["state"]) == (
            "image-research-none",
            "images-d17:d17-s01",
            "listed",
        )
        assert rows[0]["reason"] == listed[0]["reason"] and rows[0]["decision"] == "D17/D82"
        assert not aside

    def test_a_research_row_of_a_site_that_got_a_picture_since_is_superseded(self) -> None:
        listed = [{"site_id": SITE, "reason": "r"}, {"site_id": OTHER, "reason": "r"},
                  {"site_id": THIRD, "reason": "r"}]  # fmt: skip
        sites = {SITE: site(), OTHER: site(OTHER, scope_status="retired", **self.BARE)}
        rows, aside = F.run_list_rows(self.D17, "d17-s01", listed, sites)
        assert rows == [] and aside == {"superseded": 1, "retired-or-gone": 2}

    def test_a_hotlink_row_is_open_while_the_site_shows_only_its_thumbnail(self) -> None:
        listed = [{"site_id": SITE, "reason": "below the owner's floor"}]
        hotlink = site(images=0, hero=None, thumbnail_url="https://upload.wikimedia.org/x.jpg")
        rows, _ = F.run_list_rows(self.D59, "candidates-d59", listed, {SITE: hotlink})
        assert rows[0]["topic"] == "image-hotlink-uncredited" and rows[0]["decision"] == "D59"
        for moved in (site(), site(**self.BARE)):  # a credited row since, or emptied
            assert F.run_list_rows(self.D59, "x", listed, {SITE: moved}) == (
                [],
                {"superseded": 1},
            )

    def test_a_hero_row_names_its_problems(self) -> None:
        listed = [{"site_id": SITE, "problems": ["strip", "no_author"], "reason": "no qualifying row"}]  # fmt: skip
        strip = site(hero=HERO | {"width": 700, "height": 200, "author": None})
        rows, _ = F.run_list_rows(self.MOVES, "hero-moves-2026-11-06b", listed, {SITE: strip})
        assert rows[0]["reason"] == "strip, no_author: no qualifying row"
        assert rows[0]["topic"] == "hero-problem-kept" and rows[0]["decision"] == "D48/D49/D82"

    def test_a_hero_row_is_open_while_the_site_still_has_a_problem_it_names(self) -> None:
        """The list is the last plan's read. A later lane may have answered a row since: a D15
        swap of the strip, an INSERT wave, a credit repair, the flag, the thumbnail."""
        run = "hero-moves-2026-11-06b"

        def listed(*problems: str) -> list[dict[str, Any]]:
            return [{"site_id": SITE, "problems": list(problems), "reason": "no qualifying row"}]

        def reasons(problems: tuple[str, ...], now: dict[str, Any]) -> list[str]:
            rows, aside = F.run_list_rows(self.MOVES, run, listed(*problems), {SITE: now})
            assert bool(rows) != bool(aside.get("superseded"))
            return [row["reason"] for row in rows]

        no_author = site(hero=HERO | {"author": None})
        # the strip was swapped for a larger row that still names no author: one problem is left
        assert reasons(("strip", "no_author"), no_author) == ["no_author: no qualifying row"]
        # every problem the row names is answered: the row is set aside, whatever else is open
        assert reasons(("strip", "no_author"), site()) == []
        assert reasons(("strip",), no_author) == []
        # an unflagged site and a hotlinked globe picture are measured on today's row too
        assert reasons(("unflagged",), site(hero=None)) == ["unflagged: no qualifying row"]
        assert reasons(("unflagged",), site()) == []
        remote = site(thumbnail_url="https://upload.wikimedia.org/x.jpg")
        assert reasons(("hotlink",), remote) == ["hotlink: no qualifying row"]
        assert reasons(("hotlink",), site()) == []
        # a site that serves no live row any more has none of the planner's problems
        assert reasons(("unflagged", "hotlink"), site(images=0, hero=None, thumbnail_url="")) == []

    def test_a_small_hero_row_is_open_while_a_larger_live_row_stands_beside_the_hero(self) -> None:
        """D82: the planner's `small` asks for another live row of at least 1600x900, which the
        production read holds as `hero_larger` (the same measure in SQL)."""
        listed = [{"site_id": SITE, "problems": ["small"], "reason": "no qualifying row"}]
        small = HERO | {"id": 7, "width": 1200, "height": 800}

        def rows_of(now: dict[str, Any]) -> list[str]:
            rows, _ = F.run_list_rows(self.MOVES, "hero-moves-2026-11-20", listed, {SITE: now})
            return [row["reason"] for row in rows]

        assert rows_of(site(hero=small, **LARGER)) == ["small: no qualifying row"]
        # no larger row any more (excluded since), or the hero moved to a large row: answered
        assert rows_of(site(hero=small)) == []
        assert rows_of(site(hero=HERO | {"id": 58086}, **LARGER)) == []

    def test_every_research_and_hotlink_run_is_read_and_only_the_last_hero_plan(
        self, tmp_path: Path
    ) -> None:
        for rel in (
            "candidate_search/d17-2026-11-11-s01/D17_OWNER_LIST.jsonl",
            "candidate_search/d17-2026-11-12-s02/D17_OWNER_LIST.jsonl",
            "served_image/hero-moves-2026-11-06/OWNER_LIST.jsonl",
            "served_image/hero-moves-2026-11-06b/OWNER_LIST.jsonl",
            "served_image/hero-moves-2026-11-12/OWNER_LIST.jsonl",
        ):
            write_list(tmp_path, rel, [])
        read, found = F.run_list_paths(tmp_path, self.D17)
        assert [p.parent.name for p in read] == ["d17-2026-11-11-s01", "d17-2026-11-12-s02"]
        assert read == found
        read, found = F.run_list_paths(tmp_path, self.MOVES)
        assert [p.parent.name for p in read] == ["hero-moves-2026-11-12"] and len(found) == 3
        assert F.run_list_paths(tmp_path, self.D59) == ([], [])

    def test_a_site_without_a_picture_and_without_a_research_row_is_named(self) -> None:
        sites = [site(**self.BARE), site(OTHER, **self.BARE), site(THIRD),
                 site("4", scope_status="retired", **self.BARE)]  # fmt: skip
        rows = [{"site_id": OTHER, "topic": F.RESEARCH_TOPIC},
                {"site_id": SITE, "topic": "image-none"}]  # fmt: skip
        assert F.unresearched(sites, rows) == [SITE]


def tagged(sites: list[dict[str, Any]]) -> str:
    lines = [json.dumps({"kind": "site", "row": s}) for s in sites]
    lines.append(
        json.dumps({"kind": SNAPSHOT_KIND, "row": {"exported_at": "2026-10-25 10:00:00+00"}})
    )
    return "\n".join(lines) + "\n"


#: One run directory per run-list lane (`F.RUN_LISTS`), as the image lanes name them.
RUN_DIRS = {
    "images-d17": "candidate_search/d17-2026-11-11-s01/D17_OWNER_LIST.jsonl",
    "images-d59": "candidate_search/candidates-2026-11-11-d59/D59_OWNER_LIST.jsonl",
    "hero-moves": "served_image/hero-moves-2026-11-06b/OWNER_LIST.jsonl",
}


def write_list(root: Path, rel: str, rows: list[dict[str, Any]]) -> None:
    (root / rel).parent.mkdir(parents=True, exist_ok=True)
    (root / rel).write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")


def make_root(tmp_path: Path, runs: tuple[str, ...] = F.FIELD_RUNS, lanes: bool = True) -> Path:
    root = tmp_path / "remediation"
    (root / F.FOLLOWUPS).parent.mkdir(parents=True)
    (root / F.FOLLOWUPS).write_text("", encoding="utf-8")
    for name in runs:
        (root / "fields" / name).mkdir(parents=True)
        (root / "fields" / name / "RUN.json").write_text("{}", encoding="utf-8")
    if lanes:
        for lane in F.LANE_LISTS:
            write_list(
                root, lane.path, [{"site_id": OTHER, "state": "held", "reason": "unreadable"}]
            )
        for rel in RUN_DIRS.values():
            write_list(root, rel, [])
    return root


class TestTheBuild:
    def field_run(self, rows_by_run: dict[str, list[dict[str, Any]]]):  # type: ignore[no-untyped-def]
        def run(_root: Path, name: str) -> tuple[dict[str, Any], set[tuple[str, str]]]:
            rows = rows_by_run.get(name, [])
            return result(*rows), {(r["site_id"], r["field"]) for r in rows}

        return run

    def test_the_sources_come_together_in_one_list(self, tmp_path: Path) -> None:
        root = make_root(tmp_path)
        sites = [site(), site(OTHER, no_description=True), site(THIRD)]
        built = F.build(
            root=root,
            read=lambda _sql: tagged(sites),
            field_run=self.field_run({"wd5": [run_row(THIRD)]}),
        )
        assert {(r["site_id"], r["topic"]) for r in built["rows"]} == {
            (OTHER, "description-empty"),
            (OTHER, F.LANE_LISTS[0].topic),
            (OTHER, F.LANE_LISTS[1].topic),
            (THIRD, "field-period_start"),
        }
        assert built["sites"] == 2 and built["shown_sites"] == 3
        assert built["missing"] == [] and built["unregistered"] == [] and built["pending"] == 0

    def test_a_missing_source_is_named_and_refused_when_final(self, tmp_path: Path) -> None:
        root = make_root(tmp_path, runs=("wd3",), lanes=False)
        read = lambda _sql: tagged([site()])  # noqa: E731
        built = F.build(root=root, read=read, field_run=self.field_run({}))
        assert "fields/wd5" in built["missing"]
        assert F.LANE_LISTS[0].path in built["missing"]
        with pytest.raises(F.OwnerListFinalError, match="not final"):
            F.build(root=root, read=read, field_run=self.field_run({}), final=True)

    def test_an_open_pending_field_refuses_when_final(self, tmp_path: Path) -> None:
        root = make_root(tmp_path)
        read = lambda _sql: tagged([site()])  # noqa: E731
        runs = self.field_run({"wd4": [run_row(state="pending")]})
        assert F.build(root=root, read=read, field_run=runs)["pending"] == 1
        with pytest.raises(F.OwnerListFinalError, match="1 pending field question"):
            F.build(root=root, read=read, field_run=runs, final=True)
        # a pending cell whose value moved was written by a step the run does not show: not open
        moved = self.field_run({"wd4": [run_row(state="pending", stored=-3000)]})
        assert F.build(root=root, read=read, field_run=moved, final=True)["pending"] == 0

    def test_the_image_lanes_lists_are_sources_and_no_longer_unregistered(
        self, tmp_path: Path
    ) -> None:
        root = make_root(tmp_path)
        bare = {"thumbnail_url": None, "images": 0, "hero": None}
        write_list(root, RUN_DIRS["images-d17"], [{"site_id": SITE, "reason": "no candidate"}])
        write_list(root, RUN_DIRS["images-d59"], [{"site_id": OTHER, "reason": "below the floor"}])
        earlier = "served_image/hero-moves-2026-11-06/OWNER_LIST.jsonl"
        write_list(root, earlier, [{"site_id": THIRD, "problems": ["strip"], "reason": "old"}])
        write_list(
            root,
            RUN_DIRS["hero-moves"],
            [
                {"site_id": THIRD, "problems": ["no_author"], "reason": "no qualifying row"},
                # a strip the plan read, at a site a later lane left without any live row
                {"site_id": OTHER, "problems": ["strip"], "reason": "no qualifying row"},
            ],
        )
        hotlink = site(OTHER, images=0, hero=None, thumbnail_url="https://upload.wikimedia.org/x")
        uncredited = site(THIRD, hero=HERO | {"author": None})
        built = F.build(
            root=root,
            read=lambda _sql: tagged([site(**bare), hotlink, uncredited]),
            field_run=self.field_run({}),
            final=True,
        )
        listed = {(r["site_id"], r["topic"]): r for r in built["rows"] if ":" in r["source"]}
        assert set(listed) == {
            (SITE, "image-research-none"),
            (OTHER, "image-hotlink-uncredited"),
            (THIRD, "hero-problem-kept"),
        }
        assert listed[(THIRD, "hero-problem-kept")]["reason"] == "no_author: no qualifying row"
        assert built["set_aside"]["hero-moves:superseded"] == 1
        assert listed[(SITE, "image-research-none")]["source"] == "images-d17:d17-2026-11-11-s01"
        assert built["unregistered"] == [] and built["missing"] == []
        assert built["run_lists"]["hero-moves"] == [RUN_DIRS["hero-moves"]]  # the last plan only
        assert built["image_none_unresearched"] == []
        md = F.render(built)
        assert "| no usable Commons picture: why the picture research left" in md
        assert f"`{RUN_DIRS['images-d17']}`" in md and earlier not in md

    def test_a_missing_run_list_is_named_and_refused_when_final(self, tmp_path: Path) -> None:
        root = make_root(tmp_path)
        (root / RUN_DIRS["images-d59"]).unlink()
        read = lambda _sql: tagged([site()])  # noqa: E731
        built = F.build(root=root, read=read, field_run=self.field_run({}))
        assert built["missing"] == ["candidate_search/*/D59_OWNER_LIST.jsonl"]
        with pytest.raises(F.OwnerListFinalError, match="not final"):
            F.build(root=root, read=read, field_run=self.field_run({}), final=True)

    def test_a_site_without_a_picture_needs_its_research_reason_to_be_final(
        self, tmp_path: Path
    ) -> None:
        root = make_root(tmp_path)
        bare = site(thumbnail_url=None, images=0, hero=None)
        read = lambda _sql: tagged([bare])  # noqa: E731
        built = F.build(root=root, read=read, field_run=self.field_run({}))
        assert built["image_none_unresearched"] == [SITE]
        assert "**1 site(s) without a picture carry no reason**" in F.render(built)
        with pytest.raises(F.OwnerListFinalError, match="1 site\\(s\\) without a picture"):
            F.build(root=root, read=read, field_run=self.field_run({}), final=True)
        write_list(root, RUN_DIRS["images-d17"], [{"site_id": SITE, "reason": "no candidate"}])
        final = F.build(root=root, read=read, field_run=self.field_run({}), final=True)
        assert final["image_none_unresearched"] == []

    def test_the_files_are_written_and_rerunnable(self, tmp_path: Path) -> None:
        root = make_root(tmp_path)
        built = F.build(
            root=root,
            read=lambda _sql: tagged([site(no_description=True)]),
            field_run=self.field_run({}),
        )
        out = tmp_path / "out"
        F.write(built, out)
        F.write(built, out)
        lines = (out / F.OUT_JSONL).read_text(encoding="utf-8").splitlines()
        assert [json.loads(x)["topic"] for x in lines] == ["description-empty"]
        md = (out / F.OUT_MD).read_text(encoding="utf-8")
        assert "| no description (`description-empty`) | 1 | D22 |" in md
        assert "Kourion (`" in md
        assert "**Small heroes (D48).** 0 heroes are below 1600x900." in md
        assert "`hero-small` lists the 0 whose site holds another live row" in md

    def test_the_out_of_scope_artefacts_are_named_in_the_report(self, tmp_path: Path) -> None:
        root = make_root(tmp_path)
        (root / "HUMAN_ONLY.md").write_text("", encoding="utf-8")
        built = F.build(root=root, read=lambda _sql: tagged([site()]), field_run=self.field_run({}))
        assert built["out_of_scope"] == {"HUMAN_ONLY.md": F.OUT_OF_SCOPE["HUMAN_ONLY.md"]}
        assert built["unregistered"] == []
        assert "- `HUMAN_ONLY.md`: the 2026-09 questions" in F.render(built)

    def test_the_follow_ups_are_a_source_whose_open_rows_are_listed(self, tmp_path: Path) -> None:
        root = make_root(tmp_path)
        (root / F.FOLLOWUPS).write_text(
            "".join(
                json.dumps(followup(site_id)) + "\n"
                for site_id in (SYBARIS_ON_THE_TRAEIS, TICHIT, QASR_QAROUN)
            ),
            encoding="utf-8",
        )
        sites = [
            site(F.SYBARIS, name="Sybaris", **POINT),
            site(SYBARIS_ON_THE_TRAEIS, name="Sybaris on the Traeis", **POINT),
            site(TICHIT, description_start="Tichit is a town in Mauritania."),
            site(QASR_QAROUN, scope_status="retired"),
        ]
        built = F.build(
            root=root, read=lambda _sql: tagged(sites), field_run=self.field_run({}), final=True
        )
        assert [(r["site_id"], r["source"]) for r in built["rows"] if r["topic"] == F.FOLLOWUP_TOPIC] == [
            (SYBARIS_ON_THE_TRAEIS, "closeout-followups")
        ]  # fmt: skip
        assert built["followups"] == {
            "open": [SYBARIS_ON_THE_TRAEIS],
            "closed": {
                TICHIT: "the description is no longer Dhar Tichitt's",
                QASR_QAROUN: "the site is retired or gone",
            },
        }
        assert built["missing"] == [] and built["counts"][F.FOLLOWUP_TOPIC] == 1
        md = F.render(built)
        assert f"| {F.FOLLOWUP_TITLE} (`closeout-followup`) | 1 | D13/D20/D17/D82/D19 |" in md
        assert "1 still open (listed under `closeout-followup`), 2 closed; " in md
        assert f"`{TICHIT}`: the description is no longer Dhar Tichitt's" in md
        assert "Sybaris on the Traeis (`" in md

    def test_missing_follow_ups_are_named_and_refused_when_final(self, tmp_path: Path) -> None:
        root = make_root(tmp_path)
        (root / F.FOLLOWUPS).unlink()
        read = lambda _sql: tagged([site()])  # noqa: E731
        built = F.build(root=root, read=read, field_run=self.field_run({}))
        assert built["missing"] == ["final-2026-10-08/CLOSEOUT_FOLLOWUPS.jsonl"]
        assert built["followups"] == {"open": [], "closed": {}}
        with pytest.raises(F.OwnerListFinalError, match="CLOSEOUT_FOLLOWUPS.jsonl"):
            F.build(root=root, read=read, field_run=self.field_run({}), final=True)

    def test_a_listed_point_run_is_found_and_read_after_every_other_run(
        self, tmp_path: Path
    ) -> None:
        """`fields/wd5-point/<label>` (`population.py build --point`): its answer about a point
        is the last one, so a keep there closes what wd5 left unresolved."""
        root = make_root(tmp_path)
        assert F.field_run_names(root) == F.FIELD_RUNS
        for label in ("2026-11-12", "2026-11-11", "scratch"):
            (root / "fields" / F.POINT_RUNS / label).mkdir(parents=True)
        for label in ("2026-11-12", "2026-11-11"):  # `scratch` holds no RUN.json: no run
            (root / "fields" / F.POINT_RUNS / label / "RUN.json").write_text("{}", encoding="utf-8")
        assert F.field_run_names(root) == (
            *F.FIELD_RUNS,
            "wd5-point/2026-11-11",
            "wd5-point/2026-11-12",
        )
        point = run_row(field="coordinates", stored="34.664, 32.887")
        other = run_row(OTHER, field="coordinates", stored="34.664, 32.887")
        asked: list[str] = []

        def field_run(_root: Path, name: str) -> tuple[dict[str, Any], set[tuple[str, str]]]:
            asked.append(name)
            if name == "wd5":
                return result(point, other), {(SITE, "coordinates"), (OTHER, "coordinates")}
            if name == "wd5-point/2026-11-11":  # asked both again; kept SITE's point on a quote
                return result(other), {(SITE, "coordinates"), (OTHER, "coordinates")}
            return result(), set()

        built = F.build(
            root=root, read=lambda _sql: tagged([site(), site(OTHER)]), field_run=field_run
        )
        assert asked == list(F.field_run_names(root))
        assert [(r["site_id"], r["source"]) for r in built["rows"] if r["topic"] == "field-coordinates"] == [
            (OTHER, "fields-wd5-point/2026-11-11")
        ]  # fmt: skip
