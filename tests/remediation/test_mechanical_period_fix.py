"""The period correction lane (`scripts/remediation/mechanical/period_fix.py`, D121/D122/D124).

DB-less: production is a fixture export, each rule and each refusal asserted by what it produces.
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

from mechanical import apply as A  # noqa: E402
from mechanical import lane as L  # noqa: E402
from mechanical import period_fix as M  # noqa: E402
from mechanical.plan import SNAPSHOT_KIND, JournalLink, PlanError  # noqa: E402

from pipeline import periods as P  # noqa: E402
from pipeline.utils.text import UNDATED, categorize_period  # noqa: E402

RULE_SITE = "0020c4e1-21fd-4174-94ae-912703cb7ec6"
WORD_SITE = "fac97fda-c33c-46eb-9c3c-e0afd48a2eab"
OTHER = "786cada5-1feb-4c5c-9e79-b8ffdf8aacc6"
WAVE = "2026-11-07"

DERIVED = {
    "source": "WD3 decision (derived, round 0, rule:derived_rule.json)",
    "status": "RULE",
    "reasoning": "site_type 'Hillfort' lies in 'Iron Age'; the rule writes the epoch's beginning.",
}
COUNTED = {"source": "WD5 decision (counted, round 0, field_researcher:x)", "status": "MISSING"}


def live(site_id: str, start: int | None, **over: Any) -> M.Live:
    base = {
        "site_id": site_id,
        "name": "Site",
        "country": "Algeria",
        "source_id": "ancient_nerds",
        "scope_status": "in_scope",
        "lat": 36.6,
        "lon": 2.2,
        "period_start": start,
        "period_end": None,
        "period_name": UNDATED if start is None else categorize_period(start),
    }
    base.update(over)
    return M.Live(**base)


def link(jid: int, old: str | None, new: str | None, *evidence: dict[str, Any]) -> M.Link:
    return M.Link(JournalLink(jid, f"run-{jid}", "WD3/structured-fields", old, new), tuple(evidence))


def entry(site_id: str, current: int, word: str, new: int | None, jid: int) -> dict[str, Any]:
    return {
        "site_id": site_id,
        "current": current,
        "period_word": word,
        "new_regional_start": new,
        "journal_id": jid,
        "origin": "WD5 period-word answer",
        "run_stamp": f"run-{jid}",
    }


ALGERIA_ROMAN = P.start_year("Roman", country="Algeria")


class TestRules:
    def test_the_site_type_rule_s_live_start_becomes_undated(self) -> None:
        site = live(RULE_SITE, -800, country="England")
        d = M.decide_d122(site, [link(1, None, "-800", DERIVED)])
        assert d is not None and d.rule == "d122-unsourced" and d.new_start is None
        assert d.journal_id == 1 and "D122" in d.evidence[0]["source"]

    def test_a_researched_start_is_not_d122_s(self) -> None:
        assert M.decide_d122(live(RULE_SITE, -800), [link(1, None, "-800", COUNTED)]) is None

    def test_a_rule_start_that_a_later_write_replaced_is_not_d122_s(self) -> None:
        links = [link(1, None, "-800", DERIVED), link(2, "-800", "-500", COUNTED)]
        assert M.decide_d122(live(RULE_SITE, -500), links) is None

    def test_a_listed_word_gets_its_regional_year(self) -> None:
        site = live(WORD_SITE, 43)
        out = M.decide_d121(site, [link(5, None, "43", COUNTED)], entry(WORD_SITE, 43, "Roman", ALGERIA_ROMAN, 5), list_sha="x")
        assert isinstance(out, M.Decision)
        assert out.rule == "d121-regional" and out.new_start == ALGERIA_ROMAN

    def test_a_coarse_word_gives_no_year(self) -> None:
        site = live(WORD_SITE, -2500, country="England")
        out = M.decide_d121(site, [link(5, None, "-2500", COUNTED)], entry(WORD_SITE, -2500, "Bronze Age", None, 5), list_sha="x")
        assert isinstance(out, M.Decision) and out.rule == "d121-no-year" and out.new_start is None

    def test_a_value_moved_since_the_list_is_refused(self) -> None:
        site = live(WORD_SITE, 50)
        out = M.decide_d121(site, [link(5, None, "50", COUNTED)], entry(WORD_SITE, 43, "Roman", ALGERIA_ROMAN, 5), list_sha="x")
        assert isinstance(out, M.Refusal) and out.reason == "moved-since-list"

    def test_a_journal_moved_since_the_list_is_refused(self) -> None:
        site = live(WORD_SITE, 43)
        links = [link(5, None, "40", COUNTED), link(6, "40", "43", COUNTED)]
        out = M.decide_d121(site, links, entry(WORD_SITE, 43, "Roman", ALGERIA_ROMAN, 5), list_sha="x")
        assert isinstance(out, M.Refusal) and out.reason == "journal-moved-since-list"

    def test_a_table_that_moved_since_the_list_is_refused(self) -> None:
        site = live(WORD_SITE, 43)
        out = M.decide_d121(site, [link(5, None, "43", COUNTED)], entry(WORD_SITE, 43, "Roman", -999, 5), list_sha="x")
        assert isinstance(out, M.Refusal) and out.reason == "table-moved-since-list"


class TestWave:
    def test_a_listed_rule_row_is_d122_s_and_counted_once(self) -> None:
        sites = {RULE_SITE: live(RULE_SITE, 43), WORD_SITE: live(WORD_SITE, 43)}
        journal = {RULE_SITE: [link(1, None, "43", DERIVED)], WORD_SITE: [link(5, None, "43", COUNTED)]}
        d113 = [entry(RULE_SITE, 43, "Roman", ALGERIA_ROMAN, 1), entry(WORD_SITE, 43, "Roman", ALGERIA_ROMAN, 5)]
        decisions, refused, counters = M.build_decisions(sites, journal, d113, list_sha="x")
        assert {d.site_id: d.rule for d in decisions} == {RULE_SITE: "d122-unsourced", WORD_SITE: "d121-regional"}
        assert counters["d121-covered-by-d122"] == 1 and not refused

    def test_a_journal_that_does_not_end_at_the_live_value_is_refused(self) -> None:
        sites = {WORD_SITE: live(WORD_SITE, 43)}
        journal = {WORD_SITE: [link(5, None, "40", COUNTED)]}
        d113 = [entry(WORD_SITE, 43, "Roman", ALGERIA_ROMAN, 5)]
        decisions, refused, _ = M.build_decisions(sites, journal, d113, list_sha="x")
        assert not decisions and refused[0].reason == "journal-disagrees"

    def test_a_site_named_twice_is_refused(self) -> None:
        e = entry(WORD_SITE, 43, "Roman", ALGERIA_ROMAN, 5)
        with pytest.raises(PlanError):
            M.build_decisions({WORD_SITE: live(WORD_SITE, 43)}, {}, [e, e], list_sha="x")

    def test_a_cited_start_fills_an_undated_site(self) -> None:
        cited = {
            "site_id": OTHER,
            "start": -1150,
            "url": "https://example.org/p",
            "quote": "dated to the 12th century BC",
            "answered_by": "field_researcher:d124-b0001",
            "model": "anthropic/claude-sonnet-5-5 (Claude Code agent)",
            "reason": "radiocarbon",
        }
        sites = {OTHER: live(OTHER, None, country="England", lat=53.2, lon=-2.7)}
        decisions, refused, _ = M.build_decisions(sites, {}, [], list_sha="", cited=[cited])
        assert not refused and decisions[0].rule == "d124-cited" and decisions[0].new_start == -1150


class TestStep:
    def decision(self, new: int | None) -> M.Decision:
        return M.Decision(WORD_SITE, "Site", "d121-regional", 43, 5, new, "n", ({"source": "s"},))

    def test_a_year_writes_its_start_and_its_bucket(self) -> None:
        cells = M.step_verdicts(self.decision(-1500), live(WORD_SITE, 43), [link(5, None, "43")])
        assert {(c.column, c.new_value) for c in cells} == {
            ("period_start", "-1500"),
            ("period_name", categorize_period(-1500)),
        }
        assert all(c.ok and c.finding_test_id.startswith("D121/") for c in cells)

    def test_undated_clears_the_start_and_writes_the_residue_label(self) -> None:
        cells = M.step_verdicts(self.decision(None), live(WORD_SITE, 43), [link(5, None, "43")])
        assert {(c.column, c.new_value) for c in cells} == {("period_start", None), ("period_name", UNDATED)}

    def test_an_unchanged_label_is_not_written(self) -> None:
        cells = M.step_verdicts(self.decision(40), live(WORD_SITE, 43), [link(5, None, "43")])
        assert [c.column for c in cells] == ["period_start"]

    def test_a_site_moved_since_the_wave_is_refused(self) -> None:
        cells = M.step_verdicts(self.decision(-1500), live(WORD_SITE, 50), [link(5, None, "43"), link(6, "43", "50")])
        assert len(cells) == 1 and not cells[0].ok and cells[0].reason == "moved-since-wave"


class TestLane:
    def test_the_name_resolves_with_the_period_pair_and_the_label_invariant(self) -> None:
        lane = L.resolve_lane(f"period-fix-{WAVE}-s002")
        assert lane.columns == ("period_start", "period_name")
        assert UNDATED in lane.cell("period_name").allowed_new_values
        assert lane.cell("period_start").clears and lane.cell("period_start").fills_null
        assert lane.run_stamp == f"{WAVE}_mechanical-period-fix-s002"
        assert "period_start IS NULL" in A.readback_for(lane)

    @pytest.mark.parametrize("name", ["period-fix-2026-11-07", "period-fix-x-s001", "period-fix-2026-11-07-s1"])
    def test_a_malformed_name_is_no_lane(self, name: str) -> None:
        with pytest.raises(KeyError):
            M.lane_of(name)


class TestAccept:
    def rows(self) -> list[dict[str, Any]]:
        return [
            {"site_id": WORD_SITE, "column": "period_start", "old_value": "43", "new_value": None},
            {"site_id": WORD_SITE, "column": "period_name", "old_value": "1 - 500 AD", "new_value": UNDATED},
        ]

    def journal(self, stamp: str) -> list[dict[str, Any]]:
        return [
            {"row_pk": WORD_SITE, "column_name": r["column"], "run_stamp": stamp, "old_value": r["old_value"], "new_value": r["new_value"]}
            for r in self.rows()
        ]

    def test_a_written_step_has_no_deviation(self) -> None:
        lane = M.fix_lane(WAVE, 1)
        assert M.deviations(lane, self.rows(), {WORD_SITE: live(WORD_SITE, None)}, self.journal(lane.run_stamp)) == []

    def test_a_missing_write_and_a_rollback_are_deviations(self) -> None:
        lane = M.fix_lane(WAVE, 1)
        found = M.deviations(lane, self.rows(), {WORD_SITE: live(WORD_SITE, 43)}, self.journal(lane.rollback_run_stamp))
        assert any("rollback" in f for f in found) and any("does not hold" in f for f in found)

    def test_the_export_parser_reads_sites_and_journal_rows(self) -> None:
        text = "\n".join(
            json.dumps(x)
            for x in (
                {"kind": "site", "row": {"site_id": WORD_SITE, "name": "S", "country": "Algeria", "source_id": "ancient_nerds", "scope_status": None, "lat": 1.0, "lon": 2.0, "period_start": 43, "period_end": None, "period_name": "1 - 500 AD"}},
                {"kind": "journal", "row": {"id": 5, "row_pk": WORD_SITE, "run_stamp": "r", "test_id": "t", "old_value": None, "new_value": "43", "evidence": [DERIVED]}},
                {"kind": SNAPSHOT_KIND, "row": {"exported_at": "now"}},
            )
        )
        sites, journal, at = M.parse_export(text)
        assert sites[WORD_SITE].period_start == 43 and M.is_site_type_rule(journal[WORD_SITE][0]) and at == "now"
