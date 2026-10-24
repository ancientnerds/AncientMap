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
        "card_description": "A card.",
        "card_contract": "shorts-v1",
        "coord_kind": "quote",
        "period_kind": "two_source",
        "images": 4,
        "hero": dict(HERO),
        "has_qid": True,
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
            ({"hero": {**HERO, "width": 800}}, "hero-small"),
            ({"hero": {**HERO, "height": 600}}, "hero-small"),
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
        ],
    )
    def test_each_gap_is_its_own_topic(self, over: dict[str, Any], topic: str) -> None:
        rows = F.production_rows([site(**over)])
        assert topic in topics(rows)
        row = next(r for r in rows if r["topic"] == topic)
        assert row["source"] == "production" and row["decision"] == F.TOPIC_OF[topic].decision

    def test_an_empty_card_is_not_also_an_old_one(self) -> None:
        assert set(topics(F.production_rows([site(card_description="", card_contract="")]))) == {
            "card-empty"
        }

    def test_a_free_licence_asks_no_credit(self) -> None:
        free = {**HERO, "license": "Public domain", "author": None, "license_url": None}
        assert F.production_rows([site(hero=free)]) == []

    def test_a_hero_of_exactly_the_bound_is_not_small(self) -> None:
        exact = {**HERO, "width": F.HERO_WIDTH, "height": F.HERO_HEIGHT}
        assert F.production_rows([site(hero=exact)]) == []

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
            [("wd3", result(run_row()), {(SITE, "period_start")})], {SITE: site()}
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
        assert F.field_rows(runs, {SITE: site()}) == ([], F.Counter())

    def test_a_later_run_that_did_not_ask_the_field_leaves_it_open(self) -> None:
        runs = [
            ("wd3", result(run_row()), {(SITE, "period_start")}),
            ("wd5", result(), {(SITE, "coordinates")}),
        ]
        rows, _aside = F.field_rows(runs, {SITE: site()})
        assert [r["source"] for r in rows] == ["fields-wd3"]

    def test_a_value_a_later_write_replaced_is_superseded(self) -> None:
        rows, aside = F.field_rows(
            [("wd3", result(run_row(stored=-2000)), {(SITE, "period_start")})], {SITE: site()}
        )
        assert rows == [] and aside == {"superseded": 1}

    def test_a_point_is_compared_as_numbers(self) -> None:
        point = run_row(field="coordinates", stored="34.6640, 32.887")
        rows, _ = F.field_rows([("wd5", result(point), {(SITE, "coordinates")})], {SITE: site()})
        assert [r["topic"] for r in rows] == ["field-coordinates"]
        moved = run_row(field="coordinates", stored="34.7, 32.887")
        assert F.field_rows([("wd5", result(moved), {(SITE, "coordinates")})], {SITE: site()})[
            1
        ] == {"superseded": 1}

    def test_a_retired_or_gone_site_is_set_aside(self) -> None:
        runs = [
            (
                "wd3",
                result(run_row(), run_row(OTHER)),
                {(SITE, "period_start"), (OTHER, "period_start")},
            )
        ]
        rows, aside = F.field_rows(runs, {SITE: site(scope_status="retired")})
        assert rows == [] and aside == {"retired-or-gone": 2}


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
            "fields/wd5/adv/OWNER.jsonl",  # in the run's rows
            "fields/wd5/cache/x/OWNER.jsonl",  # a cache, never a list
            F.LANE_LISTS[0].path,  # registered
            "images/d17/OWNER_LIST.jsonl",  # nobody reads it
        ):
            (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
            (tmp_path / rel).write_text("", encoding="utf-8")
        found = F.unregistered_lists(tmp_path, [F.LANE_LISTS[0].path])
        assert found == ["images/d17/OWNER_LIST.jsonl"]


def tagged(sites: list[dict[str, Any]]) -> str:
    lines = [json.dumps({"kind": "site", "row": s}) for s in sites]
    lines.append(
        json.dumps({"kind": SNAPSHOT_KIND, "row": {"exported_at": "2026-10-25 10:00:00+00"}})
    )
    return "\n".join(lines) + "\n"


def make_root(tmp_path: Path, runs: tuple[str, ...] = F.FIELD_RUNS, lanes: bool = True) -> Path:
    root = tmp_path / "remediation"
    for name in runs:
        (root / "fields" / name).mkdir(parents=True)
        (root / "fields" / name / "RUN.json").write_text("{}", encoding="utf-8")
    if lanes:
        for lane in F.LANE_LISTS:
            (root / lane.path).parent.mkdir(parents=True, exist_ok=True)
            (root / lane.path).write_text(
                json.dumps({"site_id": OTHER, "state": "held", "reason": "unreadable"}) + "\n",
                encoding="utf-8",
            )
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
