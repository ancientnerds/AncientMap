"""D13: the write chain of a confirmed re-target - links, name, alias, hand-offs, the chain order.

DB-less: the live read is a dataclass (`Live`) or a fake reader that answers by the statement it is
sent; the files are written into a temporary run directory and the qid_repair output is redirected.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[2]
for _p in (REPO, REPO / "scripts" / "remediation", REPO / "output" / "remediation" / "tools"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import qid_repair as QR  # noqa: E402
from gallery_audit import chunk_writer as CW  # noqa: E402
from identity import name_write as NW  # noqa: E402
from identity import retarget as RT  # noqa: E402
from identity import retarget_plan as RP  # noqa: E402
from identity import rounds as R  # noqa: E402
from l5 import links as L5K  # noqa: E402
from mechanical import plan as MP  # noqa: E402

from tests.remediation.test_identity_b_retarget import (  # noqa: E402
    CHANIA,
    OTHER,
    TITLES,
    WP,
    answer,
    context,
    q,
)

WAVE = "2026-10-12"
KEY_NEW, KEY_OLD = "kydonia", "chania"


def web_decision(**over: Any) -> dict[str, Any]:
    """The decided web answer for Chania, as `decide_web` records it (the pages are not read here:
    the data is the shape the plan consumes)."""
    data = {
        "verdict": "RETARGET",
        "why": "The record describes the town; the ancient site is Kydonia.",
        "merge_with": None,
        "quotes": [q(WP + "Chania", "Chania is a city")],
        "target": {
            "name": {"value": "Kydonia", "quotes": [q(WP + "Kydonia", "Kydonia was an ancient city")], "note": "'Kydonia' is a name of Q200"},
            "qid": {"value": "Q200", "quotes": [q("https://www.wikidata.org/wiki/Special:EntityData/Q200.json", "Kydonia")], "note": "Q200 ('Kydonia'): P625 12 m from the point given"},
            "enwiki_title": {"value": "Kydonia", "quotes": [q(WP + "Kydonia", "Kydonia was an ancient city")], "note": "en.wikipedia 'Kydonia' is the article of Q200"},
            "source_url": {"value": WP + "Kydonia", "quotes": [q(WP + "Kydonia", "Kydonia was an ancient city")], "note": ""},
            "coordinates": {"lat": 35.519, "lon": 24.015, "quotes": [q(WP + "Kydonia", "35.519 N")], "note": "70 m from the stored point"},
        },
        "facts": {"label": "Kydonia", "description": "ancient city in Crete", "p625": {"lat": 35.519, "lon": 24.015}, "article": "Kydonia", "moved_m": 70},
    }  # fmt: skip
    data.update(over)
    return {
        "site_id": CHANIA, "status": R.DECIDED, "reason": "", "round": "r1",
        "answered_by": "web_verifier:r1-b01", "model": "m", "answered_at": "t", "data": data,
    }  # fmt: skip


def recheck_decision(verdict: str = "CONFIRM") -> dict[str, Any]:
    return {
        "site_id": CHANIA, "status": R.DECIDED, "reason": "", "round": "r1",
        "answered_by": "adversarial:r1-b01", "model": "m", "answered_at": "t",
        "data": {"verdict": verdict, "why": "read the article", "proposed": "RETARGET", "quotes": []},
    }  # fmt: skip


def live_row(**over: Any) -> dict[str, Any]:
    row = {
        "site_id": CHANIA, "source_id": "ancient_nerds", "name": "Chania", "name_normalized": KEY_OLD,
        "country": "Greece", "lat": "35.5135", "lon": "24.018", "source_url": WP + "Chania",
        "scope_status": None,
        "ext": [{"kind": "enwiki_title", "value": "Chania"}, {"kind": "wikidata_qid", "value": "Q100"}],
        "premise": "enwiki_title=Chania, wikidata_qid=Q100",
    }  # fmt: skip
    row.update(over)
    return row


def landed_row(**over: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "source_url": WP + "Kydonia",
        "ext": [
            {"kind": "enwiki_title", "value": "Kydonia"},
            {"kind": "wikidata_qid", "value": "Q200"},
        ],
        "premise": "enwiki_title=Kydonia, wikidata_qid=Q200",
    }
    base.update(over)
    return live_row(**base)


def live(*rows: dict[str, Any], **over: Any) -> RP.Live:
    base: dict[str, Any] = {"item_holders": {}, "keys": {}, "key_holders": {}, "name_rows": {}}
    base.update(over)
    return RP.Live({r["site_id"]: r for r in rows}, **base)


ASKED = {CHANIA: context()}
DECISIONS = {CHANIA: web_decision()}
RECHECKS = {CHANIA: recheck_decision()}


# ------------------------------------------------------------------------------ the wave
class TestTheWave:
    def test_only_a_confirmed_retarget_is_planned(self) -> None:
        other = {**web_decision(), "site_id": OTHER}
        keep = {
            **web_decision(),
            "site_id": "k",
            "data": {**web_decision()["data"], "verdict": "KEEP"},
        }
        webs = {CHANIA: web_decision(), OTHER: other, "k": keep}
        rechecks = {CHANIA: recheck_decision(), OTHER: recheck_decision("REJECT")}
        assert list(RP.confirmed(webs, rechecks)) == [CHANIA]
        merge = {CHANIA: {**web_decision(), "data": {**web_decision()["data"], "verdict": "MERGE"}}}
        assert RP.confirmed(merge, {CHANIA: recheck_decision()}) == {}

    def test_a_wave_takes_the_next_open_sites_once_and_a_site_is_in_one_wave_only(
        self, tmp_path: Path
    ) -> None:
        decisions = {f"s{i}": web_decision() for i in range(5)}
        first = RP.select_wave(tmp_path, "2026-10-12", decisions, limit=2, built_at="t")
        assert first["sites"] == ["s0", "s1"]
        second = RP.select_wave(tmp_path, "2026-10-12b", decisions, limit=100, built_at="t")
        assert second["sites"] == ["s2", "s3", "s4"]
        with pytest.raises(RP.ChainError, match="selected once"):
            RP.select_wave(tmp_path, "2026-10-12", decisions, limit=2, built_at="t")
        with pytest.raises(RP.ChainError, match="no site is left for a new wave"):
            RP.select_wave(tmp_path, "2026-10-13", decisions, limit=2, built_at="t")
        assert RP.load_wave(tmp_path, "2026-10-12")["sites"] == ["s0", "s1"]

    @pytest.mark.parametrize("limit", [0, 101])
    def test_a_wave_holds_one_to_a_hundred_sites(self, tmp_path: Path, limit: int) -> None:
        with pytest.raises(RP.ChainError, match="1..100"):
            RP.select_wave(tmp_path, WAVE, {"s": web_decision()}, limit=limit, built_at="t")

    def test_a_wave_that_was_never_selected_is_refused(self, tmp_path: Path) -> None:
        with pytest.raises(RP.ChainError, match="select the wave first"):
            RP.load_wave(tmp_path, WAVE)


# ------------------------------------------------------------------------------ the live read
class TestTheLiveRead:
    def reader(self, sent: list[str]):
        def read(sql: str) -> list[dict[str, Any]]:
            sent.append(sql)
            if "FROM unified_sites u WHERE u.id IN" in sql:
                return [live_row()]
            if "e.kind = 'wikidata_qid'" in sql:
                return [{"qid": "Q200", "site_id": OTHER, "name": "Kydonia"}]
            if "FROM (VALUES" in sql:
                return [{"name": "Kydonia", "key": KEY_NEW}]
            if "u.name_normalized IN" in sql:
                return [{"site_id": OTHER, "name": "Other", "name_normalized": KEY_NEW}]
            if "FROM unified_site_names n" in sql:
                return [
                    {
                        "id": 7,
                        "site_id": CHANIA,
                        "name": "Chania",
                        "name_normalized": KEY_OLD,
                        "name_type": "label",
                    }
                ]
            raise AssertionError(sql)

        return read

    def test_the_links_phase_reads_the_sites_and_the_holders_only(self) -> None:
        sent: list[str] = []
        got = RP.read_live([CHANIA], ["Q200"], ["Kydonia"], self.reader(sent), names=False)
        assert len(sent) == 2 and got.item_holders["Q200"][0]["site_id"] == OTHER
        assert got.keys == {} and got.name_rows == {}

    def test_the_names_phase_reads_the_keys_in_sql_and_the_name_rows(self) -> None:
        sent: list[str] = []
        got = RP.read_live([CHANIA], ["Q200"], ["Kydonia"], self.reader(sent), names=True)
        assert got.keys == {"Kydonia": KEY_NEW}
        assert got.key_holders[KEY_NEW][0]["site_id"] == OTHER
        assert got.name_rows[CHANIA][0]["id"] == 7
        assert any("left(lower(unaccent(" in s for s in sent), "the key is computed by Postgres"
        assert all(s.lstrip().upper().startswith("SELECT") for s in sent)

    def test_the_sites_sql_prints_the_premise_the_name_lane_checks(self) -> None:
        sql = RP.live_sites_sql([CHANIA])
        assert "string_agg(e.kind || '=' || e.value" in sql and "AS premise" in sql
        assert f"'{CHANIA}'::uuid" in sql


# ------------------------------------------------------------------------------ the links
class TestTheLinks:
    def build(self, row: dict[str, Any] | None, **over: Any) -> RP.LinkPlan:
        rows = [row] if row is not None else []
        return RP.build_links(
            over.pop("decisions", DECISIONS), over.pop("rechecks", RECHECKS),
            over.pop("asked", ASKED), live(*rows, **over),
        )  # fmt: skip

    def test_a_confirmed_retarget_becomes_the_item_the_title_and_the_source_url(self) -> None:
        plan = self.build(live_row())
        assert plan.skipped == []
        got = {(c.table, c.kind): (c.old_value, c.new_value) for c in plan.links}
        assert got == {
            ("site_external_ids", "wikidata_qid"): ("Q100", "Q200"),
            ("site_external_ids", "enwiki_title"): ("Chania", "Kydonia"),
            ("unified_sites", "source_url"): (WP + "Chania", WP + "Kydonia"),
        }
        qid = next(c for c in plan.links if c.kind == "wikidata_qid")
        assert qid.test_id == "D13/wikidata_qid" and qid.confidence == "authoritative"
        assert qid.name == "Kydonia" and qid.site_id == CHANIA
        assert any(
            "adversarial re-check (r1, adversarial:r1-b01): CONFIRM" in e for e in qid.evidence
        )
        assert any(
            e.startswith("D13 reading (r1, web_verifier:r1-b01): qid -> Q200") for e in qid.evidence
        )
        assert any("machine check: Q200" in e for e in qid.evidence)

    def test_a_link_the_site_does_not_hold_yet_is_inserted(self) -> None:
        row = live_row(ext=[{"kind": "wikidata_qid", "value": "Q100"}])
        plan = self.build(row, asked={CHANIA: context(enwiki=[])})
        title = next(c for c in plan.links if c.kind == "enwiki_title")
        assert title.old_value is None and title.new_value == "Kydonia"

    def test_a_link_that_does_not_change_is_not_a_change(self) -> None:
        row = live_row(source_url=WP + "Kydonia")
        plan = self.build(row, asked={CHANIA: context(source_url=WP + "Kydonia")})
        assert {c.kind for c in plan.links} == {"wikidata_qid", "enwiki_title"}

    @pytest.mark.parametrize(
        ("row", "reason"),
        [
            (None, "gone"),
            (live_row(source_id="lyra"), "not-curated"),
            (live_row(scope_status="retired"), "retired"),
            (live_row(name="Chania (Crete)"), "changed-since-the-question"),
            (live_row(source_url="https://example.org/x"), "changed-since-the-question"),
            (live_row(scope_status="pending"), "changed-since-the-question"),
            (live_row(ext=[{"kind": "wikidata_qid", "value": "Q999"}, {"kind": "enwiki_title", "value": "Chania"}]), "changed-since-the-question"),
            (
                live_row(
                    ext=[
                        {"kind": "enwiki_title", "value": "Chania"},
                        {"kind": "wikidata_qid", "value": "Q100"},
                        {"kind": "wikidata_qid", "value": "Q101"},
                    ]
                ),
                "changed-since-the-question",
            ),
        ],
    )  # fmt: skip
    def test_a_site_whose_state_moved_is_skipped_with_its_reason(
        self, row: dict[str, Any] | None, reason: str
    ) -> None:
        plan = self.build(row)
        assert plan.links == [] and [s["reason"] for s in plan.skipped] == [reason]

    def test_a_site_with_two_items_is_not_a_link_the_step_can_express(self) -> None:
        two = [
            {"kind": "enwiki_title", "value": "Chania"},
            {"kind": "wikidata_qid", "value": "Q100"},
            {"kind": "wikidata_qid", "value": "Q101"},
        ]
        plan = self.build(live_row(ext=two), asked={CHANIA: context(qids=["Q100", "Q101"])})
        assert [s["reason"] for s in plan.skipped] == ["links-not-one-each"]

    def test_an_item_another_record_carries_is_not_given_to_this_one(self) -> None:
        holders = {"Q200": [{"site_id": OTHER, "name": "Kydonia"}]}
        plan = self.build(live_row(), item_holders=holders)
        assert plan.links == [] and plan.skipped[0]["reason"] == "item-carried-by-another-site"
        own = {"Q200": [{"site_id": CHANIA, "name": "Chania"}]}
        assert self.build(live_row(), item_holders=own).skipped == []

    def test_two_sites_of_a_wave_are_not_given_one_item(self) -> None:
        twin = {**web_decision(), "site_id": OTHER}
        decisions = {CHANIA: web_decision(), OTHER: twin}
        asked = {CHANIA: context(), OTHER: context(site_id=OTHER)}
        plan = self.build(
            live_row(), decisions=decisions, rechecks={CHANIA: RECHECKS[CHANIA], OTHER: RECHECKS[CHANIA]},
            asked=asked,
        )  # fmt: skip
        assert plan.links == [] and plan.skipped[0]["reason"] == "item-planned-for-another-site"

    def test_an_undecided_site_stops_the_plan(self) -> None:
        stale = {CHANIA: {**web_decision(), "status": R.HELD}}
        with pytest.raises(MP.PlanError, match="DECISIONS.jsonl is stale"):
            self.build(live_row(), decisions=stale)

    def test_the_step_is_written_once_and_its_commands_are_this_wave_s(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(QR, "OUT", tmp_path / "qid_repair")
        run = tmp_path / "run"
        plan = self.build(live_row())
        out = RP.write_links(run, WAVE, plan)
        assert out == tmp_path / "qid_repair" / "d13" / WAVE / "step-001"
        assert {p.name for p in out.iterdir()} == {
            "PLAN.jsonl",
            "APPLY.sql",
            "ROLLBACK.sql",
            "PLAN.md",
        }
        wave, rows = L5K.delivered(1, RP.step_wave(WAVE))
        assert wave.run_stamp == f"{WAVE}_d13-links-001" and len(rows) == 3
        assert "source_url" in (out / "APPLY.sql").read_text("utf-8")
        assert (run / "retarget" / "waves" / WAVE / "LINKS_SKIPPED.jsonl").read_text("utf-8") == ""
        assert set(RP.link_commands(WAVE)) == set(L5K.COMMANDS)

    def test_a_wave_without_links_writes_no_step(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(QR, "OUT", tmp_path / "qid_repair")
        plan = self.build(None)
        assert RP.write_links(tmp_path / "run", WAVE, plan) is None
        skipped = (
            tmp_path / "run" / "retarget" / "waves" / WAVE / "LINKS_SKIPPED.jsonl"
        ).read_text("utf-8")
        assert json.loads(skipped)["reason"] == "gone"

    @pytest.mark.parametrize("number", [0, 1000])
    def test_a_step_number_is_one_to_nine_ninety_nine(self, number: int) -> None:
        with pytest.raises(MP.PlanError, match="not a step number"):
            RP.step_wave(WAVE)(number)


# ------------------------------------------------------------------------------ the names
LABEL_ROW = {
    "id": 7,
    "site_id": CHANIA,
    "name": "Chania",
    "name_normalized": KEY_OLD,
    "name_type": "label",
}


class TestTheNames:
    def names(self, row: dict[str, Any], **over: Any) -> NW.NamePlan:
        base = {"keys": {"Kydonia": KEY_NEW}, "name_rows": {CHANIA: [LABEL_ROW]}}
        base.update(over)
        return RP.build_names(DECISIONS, RECHECKS, live(row, **base), WAVE)

    def test_a_site_whose_links_landed_is_renamed_and_its_old_name_becomes_an_alias(self) -> None:
        plan = self.names(landed_row())
        assert plan.skipped == [] and plan.lane.name == f"retarget-name-{WAVE}"
        cells = {v.column: v for v in plan.verdicts}
        assert (cells["name"].old_value, cells["name"].new_value) == ("Chania", "Kydonia")
        assert (cells["name_normalized"].old_value, cells["name_normalized"].new_value) == (
            KEY_OLD,
            KEY_NEW,
        )
        assert cells["name"].premise == "enwiki_title=Kydonia, wikidata_qid=Q200"
        assert (cells["name"].rule, cells["name"].finding_test_id) == (
            RP.RULE_NAME,
            RP.FINDING_TEST_ID,
        )
        (alias,) = plan.aliases
        assert (alias.table, alias.column, alias.row_key) == (
            "unified_site_names",
            "name_type",
            "7",
        )
        assert (alias.old_value, alias.new_value) == ("label", "alias")
        assert "stays searchable" in alias.reason

    def test_a_site_whose_links_have_not_landed_waits_for_its_link_step(self) -> None:
        plan = self.names(live_row())
        assert plan.verdicts == [] and plan.skipped[0]["reason"] == "links-not-landed"
        half = landed_row(source_url=WP + "Chania")
        assert self.names(half).skipped[0]["reason"] == "links-not-landed"

    def test_a_site_gone_is_skipped(self) -> None:
        plan = RP.build_names(DECISIONS, RECHECKS, live(), WAVE)
        assert plan.skipped[0]["reason"] == "gone"

    def test_two_records_are_never_named_alike(self) -> None:
        taken = {KEY_NEW: [{"site_id": OTHER, "name": "Kydonia"}]}
        plan = self.names(landed_row(), key_holders=taken)
        assert plan.verdicts == [] and plan.skipped[0]["reason"] == "name-key-taken"
        mine = {KEY_NEW: [{"site_id": CHANIA, "name": "Kydonia"}]}
        assert self.names(landed_row(), key_holders=mine).skipped == []

    def test_a_name_that_is_already_the_name_is_not_written(self) -> None:
        plan = self.names(landed_row(name="Kydonia", name_normalized=KEY_NEW))
        assert plan.verdicts == [] and plan.skipped[0]["reason"] == "name-unchanged"

    def test_a_site_with_no_row_for_its_old_name_is_listed_not_guessed(self) -> None:
        plan = self.names(landed_row(), name_rows={CHANIA: []})
        assert plan.verdicts == [] and plan.skipped[0]["reason"] == "no-old-name-row"

    def test_an_old_name_that_is_already_an_alias_needs_nothing(self) -> None:
        searchable = {CHANIA: [{**LABEL_ROW, "name_type": "wikidata_alias"}]}
        plan = self.names(landed_row(), name_rows=searchable)
        assert plan.aliases == [] and plan.already_searchable == [CHANIA]
        assert {v.column for v in plan.verdicts} == {"name", "name_normalized"}

    def test_a_rename_that_keeps_the_key_writes_the_name_alone_and_needs_no_alias(self) -> None:
        decisions = {CHANIA: web_decision()}
        decisions[CHANIA]["data"]["target"]["name"]["value"] = "KYDONIA"
        plan = RP.build_names(
            decisions, RECHECKS,
            live(landed_row(name="Kydonia", name_normalized=KEY_NEW), keys={"KYDONIA": KEY_NEW},
                 name_rows={CHANIA: []}),
            WAVE,
        )  # fmt: skip
        assert [v.column for v in plan.verdicts] == ["name"] and plan.aliases == []

    def test_the_files_are_the_plan_the_skips_the_rollback_and_the_alias_chunk(
        self, tmp_path: Path
    ) -> None:
        plan = self.names(landed_row())
        mech = NW.write_name_plan(plan, "2026-10-09T03:00:00+00:00", tmp_path / "name")
        assert mech.counters == {
            "sites": 1,
            "cells": 2,
            "aliases": 1,
            "already_searchable": 0,
            "skipped": 0,
        }
        files = {p.name for p in (tmp_path / "name").iterdir()}
        assert files == {"PLAN.jsonl", "SKIPPED.jsonl", "PLAN.md", "ROLLBACK.sql"}
        first = json.loads((tmp_path / "name" / "PLAN.jsonl").read_text("utf-8").splitlines()[0])
        assert (
            first["column"] == "name"
            and first["premise"] == "enwiki_title=Kydonia, wikidata_qid=Q200"
        )
        assert first["change_key"] == f"retarget-name-{WAVE}:{CHANIA}:name"
        md = (tmp_path / "name" / "PLAN.md").read_text("utf-8")
        assert "| `" + CHANIA + "` | Chania | Kydonia | `kydonia` |" in md
        paths = NW.write_alias_chunk(plan, "retarget-name", WAVE, tmp_path / "alias")
        assert [p.name for p in paths] == ["chunk-001"]
        chunk = CW.check_delivered(paths[0])
        assert (
            chunk.run_stamp == f"retarget-name-alias-{WAVE}-001" and chunk.changes[0].row_key == "7"
        )

    def test_no_alias_no_chunk_and_a_wave_is_at_most_a_hundred_sites(self, tmp_path: Path) -> None:
        plan = self.names(landed_row(), name_rows={CHANIA: [{**LABEL_ROW, "name_type": "alias"}]})
        assert NW.write_alias_chunk(plan, "retarget-name", WAVE, tmp_path) == []
        many = NW.NamePlan(plan.lane)
        for i in range(101):
            many.verdicts += [
                MP.Verdict(
                    f"{i:08d}-0000-4000-8000-000000000000",
                    "n",
                    True,
                    "a",
                    "b",
                    "r",
                    "",
                    "",
                    False,
                    "t",
                )
            ]
        with pytest.raises(MP.PlanError, match="exceed one wave"):
            NW.name_plan(many, "t")

    def test_a_bad_wave_label_is_refused(self) -> None:
        with pytest.raises(ValueError, match="wave label"):
            NW.alias_lane("retarget-name", "2026-10")

    def test_the_two_rename_lanes_of_one_date_label_journal_their_aliases_under_their_own_stamp(
        self,
    ) -> None:
        retarget, clean = NW.alias_lane("retarget-name", WAVE), NW.alias_lane("name-clean", WAVE)
        assert retarget.stamp == f"retarget-name-alias-{WAVE}"
        assert clean.stamp == f"name-clean-alias-{WAVE}"
        assert retarget.name != clean.name
        with pytest.raises(ValueError, match="not a rename lane"):
            NW.alias_lane("spoken", WAVE)


# ------------------------------------------------------------------------------ the hand-offs
class TestTheHandoffs:
    def test_each_downstream_lane_gets_its_list_with_what_it_needs(self, tmp_path: Path) -> None:
        got = RP.handoff_records(DECISIONS, ASKED, [CHANIA], WAVE)
        assert set(got) == set(RP.HANDOFF_FILES)
        point = got["point_type"][0]
        assert (point["lat"], point["lon"], point["old_lat"]) == (35.519, 24.015, 35.5135)
        assert point["moved_m"] == 70 and point["item_label"] == "Kydonia"
        assert point["quotes"][0]["quote"] == "35.519 N"
        assert got["description"][0]["enwiki_title"] == "Kydonia"
        assert (
            "SCOPE4.v3.json" in got["description"][0]["ask"]
            and "lane WN" in got["description"][0]["ask"]
        )
        assert got["description"][0]["old_description_lane"] == "L"
        assert "Commons category" in got["gallery"][0]["ask"]
        assert "D12" in got["period"][0]["ask"] and "stale" in got["card"][0]["ask"]
        counts = RP.write_handoffs(tmp_path, WAVE, got)
        assert counts == dict.fromkeys(RP.HANDOFF_FILES, 1)
        for stage, name in RP.HANDOFF_FILES.items():
            line = (tmp_path / "retarget" / "waves" / WAVE / name).read_text("utf-8")
            assert json.loads(line)["site_id"] == CHANIA, stage


# ------------------------------------------------------------------------------ the chain
LANDED: dict[str, list[str]] = {"s1": [], "s2": []}


class TestTheChain:
    @pytest.fixture
    def run(self, tmp_path: Path) -> Path:
        RP.select_wave(
            tmp_path, WAVE, {"s1": web_decision(), "s2": web_decision()}, limit=100, built_at="t"
        )
        return tmp_path

    def test_a_stage_starts_only_on_sites_that_finished_the_stages_before_it(
        self, run: Path
    ) -> None:
        assert RP.chain_ready(run, "links") == ["s1", "s2"]
        assert RP.chain_ready(run, "name") == []
        RP.chain_done(run, WAVE, "links", "stamp-l", unfinished=LANDED, at="t1")
        assert RP.chain_ready(run, "name") == ["s1", "s2"] and RP.chain_ready(run, "links") == []
        RP.chain_done(run, WAVE, "name", "stamp-n", ["s1"], unfinished=LANDED, at="t2")
        RP.chain_done(run, WAVE, "alias", "stamp-a", ["s1"], unfinished=LANDED, at="t3")
        assert RP.chain_ready(run, "point_type") == ["s1"] and RP.chain_ready(run, "name") == ["s2"]
        assert RP.chain_ready(run, "alias") == []
        table = {r["site_id"]: r for r in RP.chain_table(run)}
        assert (
            table["s1"]["done"] == ["links", "name", "alias"]
            and table["s1"]["next"] == "point_type"
        )
        assert table["s2"]["done"] == ["links"] and table["s2"]["next"] == "name"

    def test_the_stages_are_in_order_the_hand_offs_after_the_writes(self) -> None:
        assert RP.CHAIN == (
            "links",
            "name",
            "alias",
            "point_type",
            "description",
            "gallery",
            "period",
            "card",
        )
        assert set(RP.HANDOFF_FILES) == set(RP.CHAIN[3:])

    def test_a_stage_cannot_be_recorded_out_of_order_twice_or_for_a_stranger(
        self, run: Path
    ) -> None:
        with pytest.raises(RP.ChainError, match="s1: name waits for links"):
            RP.chain_done(run, WAVE, "name", "x", unfinished=LANDED)
        RP.chain_done(run, WAVE, "links", "x", unfinished=LANDED)
        with pytest.raises(RP.ChainError, match="recorded already"):
            RP.chain_done(run, WAVE, "links", "x", unfinished=LANDED)
        with pytest.raises(RP.ChainError, match="not sites of wave"):
            RP.chain_done(run, WAVE, "name", "x", ["s9"], unfinished=LANDED)
        with pytest.raises(RP.ChainError, match="not a stage of the chain"):
            RP.chain_done(run, WAVE, "paint", "x")
        with pytest.raises(RP.ChainError, match="run stamp that wrote it"):
            RP.chain_done(run, WAVE, "name", " ", unfinished=LANDED)
        with pytest.raises(RP.ChainError, match="not a stage of the chain"):
            RP.chain_ready(run, "paint")

    def test_a_refused_record_writes_nothing_for_any_site(self, run: Path) -> None:
        RP.chain_done(run, WAVE, "links", "x", ["s1"], unfinished=LANDED)
        with pytest.raises(RP.ChainError, match="s2: name waits for links"):
            RP.chain_done(run, WAVE, "name", "x", unfinished=LANDED)
        assert RP.chain_state(run) == {
            "s1": {"links": {"stamp": "x", "at": RP.chain_state(run)["s1"]["links"]["at"]}}
        }

    def test_links_name_and_alias_are_recorded_only_against_a_read_back_of_production(
        self, run: Path
    ) -> None:
        for stage in RP.READ_BACK_STAGES:
            with pytest.raises(RP.ChainError, match="against a read-back of production"):
                RP.chain_done(run, WAVE, stage, "x")
        assert RP.chain_state(run) == {}

    def test_a_site_that_has_not_landed_is_not_recorded_done_and_nothing_is_written(
        self, run: Path
    ) -> None:
        with pytest.raises(RP.ChainError, match="s2: links has not landed: a plan skipped it"):
            RP.chain_done(
                run, WAVE, "links", "x", unfinished={"s1": [], "s2": ["a plan skipped it: gone"]}
            )
        with pytest.raises(RP.ChainError, match="s2: links has not landed: it was not read back"):
            RP.chain_done(run, WAVE, "links", "x", unfinished={"s1": []})
        assert RP.chain_state(run) == {}
        RP.chain_done(run, WAVE, "links", "x", ["s1"], unfinished={"s1": []})
        assert RP.chain_ready(run, "name") == ["s1"]


class TestWhatKeepsAStageFromHavingLanded:
    def unfinished(self, stage: str, row: dict[str, Any] | None, **over: Any):
        rows = over.pop("rows", None)
        name_rows = {CHANIA: rows if rows is not None else [
            {"id": 7, "site_id": CHANIA, "name": "Chania", "name_normalized": "chania", "name_type": "alias"}]}  # fmt: skip
        return RP.unfinished(
            stage,
            DECISIONS,
            ASKED,
            live(*([row] if row else []), keys={"Kydonia": "kydonia"}, name_rows=name_rows),
            over.get("skipped", {}),
        )[CHANIA]

    def test_a_site_a_plan_skipped_or_that_is_gone_has_not_landed(self) -> None:
        row = landed_row(name="Kydonia", name_normalized="kydonia")
        assert self.unfinished("links", row, skipped={CHANIA: "links-not-landed: waits"}) == [
            "a plan skipped it: links-not-landed: waits"
        ]
        assert self.unfinished("alias", None) == ["the row is gone"]

    def test_each_stage_reads_back_itself_and_the_stages_before_it_only(self) -> None:
        links_only = landed_row()  # links landed, name and alias not yet
        assert self.unfinished("links", links_only) == []
        assert [d.split(" is ")[0] for d in self.unfinished("name", links_only)] == ["name"]
        assert self.unfinished("name", landed_row(name="Kydonia", name_normalized="kydonia")) == []
        old_label = [{"id": 7, "site_id": CHANIA, "name": "Chania", "name_normalized": "chania", "name_type": "label"}]  # fmt: skip
        named = landed_row(name="Kydonia", name_normalized="kydonia")
        assert self.unfinished("name", named, rows=old_label) == []
        assert "not searchable" in self.unfinished("alias", named, rows=old_label)[0]
        assert self.unfinished("alias", named) == []
        stale = landed_row(source_url=WP + "Chania", name="Kydonia", name_normalized="kydonia")
        assert "source_url" in self.unfinished("alias", stale)[0]


class TestTheReadBack:
    def verify(
        self,
        row: dict[str, Any] | None,
        *,
        skipped: dict[str, str] | None = None,
        rows: list | None = None,
    ):
        keys = {"Kydonia": "kydonia"}
        name_rows = {CHANIA: rows if rows is not None else [
            {"id": 7, "site_id": CHANIA, "name": "Chania", "name_normalized": "chania", "name_type": "alias"}]}  # fmt: skip
        return RP.verify_wave(
            DECISIONS,
            ASKED,
            live(*([row] if row else []), keys=keys, name_rows=name_rows),
            skipped or {},
        )

    def landed(self, **over: Any) -> dict[str, Any]:
        return landed_row(**{"name": "Kydonia", "name_normalized": "kydonia", **over})

    def test_a_wave_that_landed_has_no_deviation(self) -> None:
        (got,) = self.verify(self.landed())
        assert got == {"site_id": CHANIA, "state": "landed", "deviations": []}

    def test_a_site_a_plan_skipped_is_reported_as_skipped_not_as_a_deviation(self) -> None:
        (got,) = self.verify(None, skipped={CHANIA: "links-not-landed: waits"})
        assert got["state"] == "skipped" and got["deviations"] == [] and "waits" in got["why"]

    def test_a_row_that_is_gone_is_a_deviation(self) -> None:
        (got,) = self.verify(None)
        assert got["state"] == "gone" and got["deviations"] == ["the row is gone"]

    @pytest.mark.parametrize(
        ("row", "rows", "match"),
        [
            ({"ext": [{"kind": "wikidata_qid", "value": "Q100"}, {"kind": "enwiki_title", "value": "Kydonia"}]}, None, "wikidata_qid is"),
            ({"ext": [{"kind": "wikidata_qid", "value": "Q200"}, {"kind": "enwiki_title", "value": "Chania"}]}, None, "enwiki_title is"),
            ({"source_url": WP + "Chania"}, None, "source_url is"),
            ({"name": "Chania", "name_normalized": "chania"}, None, "name is 'Chania'"),
            ({"name_normalized": "chania"}, None, "name_normalized is 'chania'"),
            ({}, [], "old name 'Chania' is not searchable"),
            ({}, [{"id": 7, "site_id": CHANIA, "name": "Chania", "name_normalized": "chania", "name_type": "label"}], "not searchable"),
        ],
    )  # fmt: skip
    def test_every_way_production_can_differ_from_the_plan(
        self, row: dict[str, Any], rows: list | None, match: str
    ) -> None:
        (got,) = self.verify(self.landed(**row), rows=rows)
        assert got["state"] == "deviates" and any(match in d for d in got["deviations"]), got
