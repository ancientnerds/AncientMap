"""D20 scope window population and D25 parent candidates."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
if str(REPO / "scripts" / "remediation") not in sys.path:
    sys.path.insert(0, str(REPO / "scripts" / "remediation"))

from identity import common, export, parents, scope_window  # noqa: E402

from tests.remediation.identity_fixtures import export_of, ext, site  # noqa: E402

HADRIAN_ID = f"{export.HADRIANS_WALL_PATH_PREFIX}-0000-4000-8000-000000000001"


def hadrian(**over):
    return site(id=HADRIAN_ID, name=scope_window.HADRIANS_WALL_PATH_NAME, **over)


def journal(site_id, column="period_start", stamp="2026-09-26d_fields-wd3-s004", **over):
    row = {
        "site_id": site_id,
        "column_name": column,
        "run_stamp": stamp,
        "confidence": "one_source",
        "old_value": "400",
        "new_value": "1800",
        "applied_at": "2026-09-26 10:00:00+00",
        "models": "anthropic/claude-sonnet-5-5",
    }
    row.update(over)
    return row


class TestTheStampFamily:
    def test_a_field_lane_stamp_is_its_lane(self) -> None:
        assert scope_window.stamp_family("2026-09-26d_fields-wd1-s018") == "fields-wd1"
        assert scope_window.stamp_family("2026-09-26_fields-wd3-s004") == "fields-wd3"

    def test_a_phase_three_chunk_is_phase3(self) -> None:
        assert scope_window.stamp_family("phase3:batch-0288:chunk-0001") == "phase3"

    def test_another_stamp_loses_its_date_and_its_step(self) -> None:
        assert (
            scope_window.stamp_family("2026-09-25_mechanical-journal-reversal-3")
            == "mechanical-journal-reversal-3"
        )
        assert scope_window.stamp_family("2026-09-23_scope-e4-s002") == "scope-e4"


class TestTheDateTheWindowTests:
    def test_the_end_of_the_period_is_the_date(self) -> None:
        assert scope_window.date_used({"period_start": -500, "period_end": 100}) == 100

    def test_an_end_of_zero_or_none_falls_through_to_the_start(self) -> None:
        assert scope_window.date_used({"period_start": 1800, "period_end": 0}) == 1800
        assert scope_window.date_used({"period_start": 1800, "period_end": None}) == 1800


class TestThePopulation:
    def test_a_site_inside_the_window_is_not_in_the_population(self) -> None:
        records, counts = scope_window.build(export_of([site(), hadrian()]))
        assert [r["name"] for r in records] == ["Hadrian's Wall Path"]
        assert counts["population"] == 1

    def test_the_sql_windows_verdict_is_trusted_not_recomputed(self) -> None:
        outside = site(name="Late", outside_window=True, period_start=1800)
        records, _ = scope_window.build(export_of([outside, hadrian()]))
        assert [r["groups"] for r in records if r["name"] == "Late"] == [["outside_window"]]

    def test_a_pending_site_is_in_the_population_inside_the_window_too(self) -> None:
        pending = site(name="Pending", scope_status="pending")
        records, _ = scope_window.build(export_of([pending, hadrian()]))
        assert [r["groups"] for r in records if r["name"] == "Pending"] == [["pending"]]

    def test_a_site_can_be_in_several_groups(self) -> None:
        both = site(name="Both", outside_window=True, scope_status="pending")
        records, counts = scope_window.build(export_of([both, hadrian()]))
        assert [r["groups"] for r in records if r["name"] == "Both"] == [
            ["outside_window", "pending"]
        ]
        assert counts["group_outside_window"] == 1 and counts["group_pending"] == 1

    def test_a_museum_is_flagged_for_the_museum_question(self) -> None:
        museum = site(name="Museum", site_type="Museum", outside_window=True)
        records, counts = scope_window.build(export_of([museum, hadrian()]))
        flagged = {r["name"]: r["museum_question"] for r in records}
        assert flagged["Museum"] is True and flagged["Hadrian's Wall Path"] is False
        assert counts["museum_question"] == 1 and counts["museum_undecided"] == 1

    def test_the_footpath_must_be_exactly_one_site_with_the_pinned_name(self) -> None:
        with pytest.raises(common.IdentityError, match="is not one shown site"):
            scope_window.build(export_of([site()]))
        wrong = site(id=HADRIAN_ID, name="Something else")
        with pytest.raises(common.IdentityError, match="is not one shown site"):
            scope_window.build(export_of([wrong]))


class TestTheProvenance:
    def test_the_last_write_of_each_column_is_kept_with_its_family(self) -> None:
        late = site(name="Late", outside_window=True)
        records, counts = scope_window.build(
            export_of(
                [late, hadrian()],
                period_journal=[
                    journal(late["id"], "period_start"),
                    journal(late["id"], "period_name", "2026-09-26d_fields-wd1-s018"),
                ],
            )
        )
        record = next(r for r in records if r["name"] == "Late")
        assert set(record["period_writes"]) == {"period_start", "period_name"}
        assert record["period_writes"]["period_start"]["family"] == "fields-wd3"
        assert record["period_writes"]["period_start"]["models"] == "anthropic/claude-sonnet-5-5"
        assert record["origin"] == "fields-wd3"
        assert counts["origin_fields-wd3"] == 1

    def test_a_period_the_journal_never_touched_is_an_import(self) -> None:
        late = site(name="Late", outside_window=True)
        records, counts = scope_window.build(export_of([late, hadrian()]))
        assert {r["origin"] for r in records} == {scope_window.ORIGIN_IMPORT}
        assert counts["origin_import"] == 2

    def test_a_wd3_or_wd4_period_is_rechecked_first_and_a_wd1_one_is_not(self) -> None:
        a, b, c = (site(outside_window=True) for _ in range(3))
        records, counts = scope_window.build(
            export_of(
                [a, b, c, hadrian()],
                period_journal=[
                    journal(a["id"], stamp="2026-09-26_fields-wd3-s001"),
                    journal(b["id"], stamp="2026-09-26_fields-wd4-s001"),
                    journal(c["id"], stamp="2026-09-26d_fields-wd1-s001"),
                ],
            )
        )
        flags = {r["id"]: r["recheck_d10"] for r in records}
        assert flags[a["id"]] and flags[b["id"]] and not flags[c["id"]]
        assert counts["recheck_d10"] == 2

    def test_the_period_the_window_tested_is_reported(self) -> None:
        late = site(name="Late", outside_window=True, period_start=1800, period_end=0)
        records, _ = scope_window.build(export_of([late, hadrian()]))
        assert next(r for r in records if r["name"] == "Late")["date_used"] == 1800


class TestTheParentCandidates:
    def place(self, name, lat=38.0, lon=23.0, country="Egypt"):
        return site(name=name, lat=lat, lon=lon, country=country)

    def test_the_shorter_name_is_the_parent_of_the_longer_one(self) -> None:
        child = self.place("Abu Simbel Small Temple", lon=23.001)
        parent = self.place("Abu Simbel")
        pairs = parents.candidate_pairs([parent, child])
        assert [(p["id"], c["id"]) for _, p, c in pairs] == [(parent["id"], child["id"])]

    def test_names_with_the_same_significant_words_are_not_a_pair(self) -> None:
        a, b = self.place("Abu Simbel"), self.place("Temple of Abu Simbel")
        assert parents.candidate_pairs([a, b]) == []

    def test_names_that_merely_overlap_are_not_a_pair(self) -> None:
        a, b = self.place("Abu Simbel"), self.place("Abu Gorab Sun Temple")
        assert parents.candidate_pairs([a, b]) == []

    def test_two_countries_are_not_a_pair(self) -> None:
        a = self.place("Abu Simbel")
        b = self.place("Abu Simbel Small Temple", country="Sudan")
        assert parents.candidate_pairs([a, b]) == []

    def test_more_than_two_kilometres_apart_is_not_a_pair(self) -> None:
        a = self.place("Abu Simbel")
        near = self.place("Abu Simbel Small Temple", lon=23.015)  # about 1.3 km
        far = self.place("Abu Simbel Hathor Shrine", lon=23.03)  # about 2.6 km
        pairs = parents.candidate_pairs([a, near, far])
        assert [c["id"] for _, _, c in pairs] == [near["id"]]

    def test_the_sweep_stops_at_the_latitude_reach(self, monkeypatch) -> None:
        a = self.place("Abu Simbel")
        far = self.place("Abu Simbel Small Temple", lat=39.0)
        calls = []
        monkeypatch.setattr(common, "metres", lambda *args: calls.append(args) or 0.0)
        assert parents.candidate_pairs([a, far]) == []
        assert calls == []

    def test_the_pairs_are_ordered_by_distance(self) -> None:
        a = self.place("Abu Simbel")
        far = self.place("Abu Simbel Hathor Shrine", lon=23.012)
        near = self.place("Abu Simbel Small Temple", lon=23.002)
        pairs = parents.candidate_pairs([a, far, near])
        assert [c["id"] for _, _, c in pairs] == [near["id"], far["id"]]

    def test_the_parent_record_lists_its_children_nearest_first_with_the_flags(self) -> None:
        a = self.place("Abu Simbel")
        near = self.place("Abu Simbel Small Temple", lon=23.002)
        far = self.place("Abu Simbel Hathor Shrine", lon=23.012)
        records, counts = parents.build(
            export_of(
                [a, far, near],
                ext_ids=[
                    ext(a["id"], "wikidata_qid", "Q1"),
                    ext(near["id"], "wikidata_qid", "Q1"),
                ],
            )
        )
        assert len(records) == 1 and records[0]["n_children"] == 2
        children = records[0]["children"]
        assert [c["id"] for c in children] == [near["id"], far["id"]]
        assert children[0]["shared_qid"] is True and children[1]["shared_qid"] is False
        assert records[0]["parent_is_child"] is False
        assert counts["pairs"] == 2 and counts["parents"] == 1 and counts["children"] == 2

    def test_a_chain_is_flagged_and_a_child_with_two_parents_is_flagged(self) -> None:
        root = self.place("Abu Simbel")
        mid = self.place("Abu Simbel Temple Hall", lon=23.001)
        leaf = self.place("Abu Simbel Temple Hall Annex", lon=23.002)
        records, counts = parents.build(export_of([root, mid, leaf]))
        by_name = {r["parent"]["name"]: r for r in records}
        assert by_name["Abu Simbel Temple Hall"]["parent_is_child"] is True
        assert by_name["Abu Simbel"]["parent_is_child"] is False
        leaf_entries = [c for r in records for c in r["children"] if c["id"] == leaf["id"]]
        assert all(len(c["competing_parents"]) == 1 for c in leaf_entries)
        assert counts["children_with_competing_parents"] == 1
        assert counts["parents_that_are_children"] == 1

    def test_the_parent_column_already_set_is_counted(self) -> None:
        a = site(parent_site_id="some-id")
        _, counts = parents.build(export_of([a]))
        assert counts["parent_site_id_already_set"] == 1
