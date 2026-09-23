"""The E4 scope lane: four rules, each decision quoted from the site's own row, nothing deleted.

`build_scope_plan` is a pure function of an export, T11's findings, the reviewed decisions and
the Wikidata names. The findings here are T11's own `Finding` objects with the notes T11 writes;
the T11 run itself needs the geo stack and Natural Earth, so the test that runs it skips with its
reason when either is absent.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[2]
if str(REPO / "scripts" / "remediation") not in sys.path:
    sys.path.insert(0, str(REPO / "scripts" / "remediation"))

from census.model import Confidence, Evidence, Finding, Proposal, Severity  # noqa: E402
from mechanical import apply as A  # noqa: E402
from mechanical import lane as L  # noqa: E402
from mechanical import plan as P  # noqa: E402
from mechanical import scope as S  # noqa: E402

FORT = "8c159d7f-d954-44fc-aab9-6b7841d68a35"
GATE = "17cf019a-913c-4967-b17c-ceabe8d1ba3b"
MUSEUM = "660f8d4f-9fbd-43ea-8431-18c9327e81ea"
UNDATED = "2133d54c-f352-4325-ae0c-dd532f9a65d3"
DUP_A = "f6b6e039-36f1-4107-b730-dc2aa34b7a92"
DUP_B = "f5ca382a-3725-4cbb-961a-6afbf5c21507"
NE_CACHE = (
    REPO / "output" / "remediation" / "cache" / "naturalearth" / "ne_10m_admin_0_countries.shp"
)
needs_t11 = pytest.mark.skipif(
    importlib.util.find_spec("geopandas") is None or not NE_CACHE.exists(),
    reason=f"T11 needs geopandas and the Natural Earth cache ({NE_CACHE})",
)


def site(site_id: str, **over: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "id": site_id,
        "name": "a site",
        "source_id": "ancient_nerds",
        "site_type": "Fortress/citadel",
        "country": "Pakistan",
        "lat": 34.03,
        "lon": 71.25,
        "period_start": 1837,
        "period_end": None,
        "period_name": "1500+ AD",
        "description": "A 19th-century fortress.",
        "source_url": "https://en.wikipedia.org/wiki/X",
        "created_at": "2026-03-04 21:07:57.660461",
        "scope_status": None,
        "scope_reason": None,
        "premise": f"premise-{site_id[:8]}",
        "links": 0,
        "images": 0,
        "citations": 0,
        "ext": None,
    }
    base.update(over)
    return base


def finding(site_id: str, kind: str, note: str) -> Finding:
    return Finding(
        site_id=site_id,
        test_id=kind,
        field="scope_status",
        severity=Severity.SEVERE,
        dimension="SCOPE",
        current_value=None,
        proposal=Proposal.REVIEW,
        confidence=Confidence.AUTHORITATIVE,
        note=note,
        evidence=[Evidence(source="pipeline/normalizers/dates.py:85-88", quote="date <= cutoff")],
    )


WINDOW_NOTE = (
    "period_start 1837 is 1337 years past the rest of world cutoff of 500 AD, and E4 says an "
    "out-of-scope site is flagged and hidden, never deleted. Natural Earth puts the point in X"
)


def decision(site_id: str, name: str, rule: str, status: str, quote: str) -> S.Decision:
    return S.Decision(site_id, name, rule, status, quote, "reviewed")


def export(*sites: dict[str, Any], pairs: tuple[dict[str, Any], ...] = ()) -> S.Export:
    return S.Export(sites=tuple(sites), pairs=pairs, journal=(), exported_at="t")


def build(
    ex: S.Export,
    findings: dict[str, Finding],
    decisions: dict[str, S.Decision] | None = None,
    entities: dict[str, Any] | None = None,
) -> S.ScopePlan:
    return S.build_scope_plan(ex, findings, decisions or {}, entities or {}, built_at="t")


def status_of(result: S.ScopePlan) -> dict[str, tuple[str, str]]:
    return {d.site["id"]: (d.rule, d.status) for d in result.decisions}


class TestRuleA:
    def test_out_of_the_window_retires_with_t11_s_own_words(self) -> None:
        result = build(export(site(FORT)), {FORT: finding(FORT, S.OUT_OF_WINDOW, WINDOW_NOTE)})
        (d,) = result.decisions
        assert (d.rule, d.status) == ("a", "retired")
        assert (
            d.reason
            == "E3: period_start 1837 is 1337 years past the rest of world cutoff of 500 AD"
        )

    def test_a_quote_dating_part_of_the_site_inside_the_window_keeps_it_pending(self) -> None:
        gate = site(
            GATE, name="Damascus Gate", description="A Roman gate of c. 135 AD lies beneath."
        )
        quote = "A Roman gate of c. 135 AD lies beneath."
        result = build(
            export(gate),
            {GATE: finding(GATE, S.OUT_OF_WINDOW, WINDOW_NOTE)},
            {GATE: decision(GATE, "Damascus Gate", "a", "pending", quote)},
        )
        (d,) = result.decisions
        assert (d.status, d.evidence[0]["quote"]) == ("pending", quote)

    def test_rule_a_can_only_turn_a_retirement_into_pending(self) -> None:
        result = build(
            export(site(FORT)),
            {FORT: finding(FORT, S.OUT_OF_WINDOW, WINDOW_NOTE)},
            {FORT: decision(FORT, "a site", "a", "in_scope", "A 19th-century fortress.")},
        )
        assert not result.decisions and result.refused[0][1] == "decision-not-allowed"


class TestTheQuotes:
    def test_a_quote_the_description_does_not_hold_is_refused(self) -> None:
        result = build(
            export(site(FORT)),
            {FORT: finding(FORT, S.OUT_OF_WINDOW, WINDOW_NOTE)},
            {FORT: decision(FORT, "a site", "a", "pending", "Founded by the Romans.")},
        )
        assert result.refused[0][1] == "quote-not-in-description" and not result.decisions

    def test_a_decision_that_names_another_site_is_refused(self) -> None:
        result = build(
            export(site(FORT)),
            {FORT: finding(FORT, S.OUT_OF_WINDOW, WINDOW_NOTE)},
            {FORT: decision(FORT, "Jamrud Fort", "a", "pending", "A 19th-century fortress.")},
        )
        assert result.refused[0][1] == "decision-names-another-site"

    def test_a_decision_without_a_finding_is_refused(self) -> None:
        result = build(
            export(site(FORT)), {}, {FORT: decision(FORT, "a site", "b", "pending", "A")}
        )
        assert result.refused[0][1] == "decision-without-finding"


class TestRuleBAndD:
    def test_an_undated_row_is_pending_unless_its_own_source_places_it_outside(self) -> None:
        undated = site(UNDATED, period_start=None, description="A sanctuary notified in 1974.")
        findings = {UNDATED: finding(UNDATED, S.UNDATED, "no date")}
        assert status_of(build(export(undated), findings)) == {UNDATED: ("b", "pending")}
        retired = build(
            export(undated),
            findings,
            {UNDATED: decision(UNDATED, "a site", "b", "retired", "notified in 1974")},
        )
        assert status_of(retired) == {UNDATED: ("b", "retired")}

    def test_an_undated_museum_is_kept_by_the_museum_rule_and_nothing_else_is(self) -> None:
        museum = site(UNDATED, site_type="Museum", period_start=None, description="Roman finds.")
        keep = {UNDATED: decision(UNDATED, "a site", "d", "in_scope", "Roman finds.")}
        findings = {UNDATED: finding(UNDATED, S.UNDATED, "no date")}
        assert status_of(build(export(museum), findings, keep)) == {UNDATED: ("d", "in_scope")}
        not_a_museum = {**museum, "site_type": "Cairn"}
        refused = build(export(not_a_museum), findings, keep)
        assert refused.refused[0][1] == "decision-not-allowed"

    def test_a_museum_past_the_cutoff_needs_a_reviewed_decision(self) -> None:
        museum = site(MUSEUM, site_type="Museum", period_start=1903, description="Mycenaean finds.")
        findings = {MUSEUM: finding(MUSEUM, S.MUSEUM, "founding year")}
        assert build(export(museum), findings).refused[0][1] == "museum-needs-a-decision"
        keep = {MUSEUM: decision(MUSEUM, "a site", "d", "in_scope", "Mycenaean finds.")}
        assert status_of(build(export(museum), findings, keep)) == {MUSEUM: ("d", "in_scope")}
        leave = {MUSEUM: decision(MUSEUM, "a site", "d", "pending", "Mycenaean finds.")}
        assert build(export(museum), findings, leave).refused[0][1] == "museum-needs-a-decision"


def entity(*names: str) -> dict[str, Any]:
    return {
        "labels": {"en": {"value": names[0]}},
        "aliases": {"de": [{"value": n} for n in names[1:-1]]},
        "sitelinks": {"enwiki": {"title": names[-1]}},
    }


class TestRuleC:
    PAIR = {"a": DUP_A, "b": DUP_B, "qid": "Q1242421", "metres": 7.1}

    def sites(self, **b: Any) -> tuple[dict[str, Any], dict[str, Any]]:
        return (
            site(DUP_A, name="Ballymacaldrack Court Tomb", links=5, citations=3, images=3),
            site(DUP_B, name="Dooey's Cairn", links=0, citations=2, images=3, **b),
        )

    def test_two_names_of_one_item_within_100_m_are_one_site(self) -> None:
        a, b = self.sites()
        names = {
            "Q1242421": entity("Dooey's Cairn", "Ballymacaldrack  court tomb", "Dooey's Cairn")
        }
        result = build(export(a, b, pairs=(self.PAIR,)), {}, entities=names)
        (d,) = result.decisions
        assert (d.site["id"], d.rule, d.status, d.reason) == (
            DUP_B,
            "c",
            "retired",
            f"duplicate_of:{DUP_A}",
        )

    def test_a_name_that_is_not_one_of_the_item_s_is_no_duplicate(self) -> None:
        a, b = self.sites()
        names = {"Q1242421": entity("Dooey's Cairn", "Dooey's Cairn")}
        result = build(export(a, b, pairs=(self.PAIR,)), {}, entities=names)
        assert not result.decisions and result.others[0]["names_known"] == [False, True]

    def test_the_older_row_survives_before_the_one_with_more_links(self) -> None:
        a, b = self.sites(created_at="2026-03-01 00:00:00")
        names = {"Q1242421": entity("Dooey's Cairn", "Ballymacaldrack Court Tomb", "x")}
        (d,) = build(export(a, b, pairs=(self.PAIR,)), {}, entities=names).decisions
        assert d.site["id"] == DUP_A and d.reason == f"duplicate_of:{DUP_B}"

    def test_a_survivor_that_is_retired_keeps_its_duplicate(self) -> None:
        a, b = self.sites()
        a = {**a, "scope_status": "retired"}
        names = {"Q1242421": entity("Dooey's Cairn", "Ballymacaldrack Court Tomb", "x")}
        result = build(export(a, b, pairs=(self.PAIR,)), {}, entities=names)
        assert ("survivor-retired" in {r[1] for r in result.refused}) and not any(
            d.site["id"] == DUP_B for d in result.decisions
        )

    def test_names_fold_case_width_and_spaces_but_nothing_else(self) -> None:
        assert S.fold("Ｔarxien  TEMPLES ") == "tarxien temples"
        assert S.fold("Tarxien Temples") != S.fold("Tarxien Temple")


class TestTheWindowPredicate:
    def test_the_residual_is_the_project_s_own_rule_negated(self) -> None:
        """`passes_date_cutoff` includes a row without a date or a longitude; the SQL must too, or
        the read-back would count the 15 undated rows as outside the window."""
        from pipeline.normalizers import dates

        sql = L.outside_e3_window()
        assert sql.startswith("(lon IS NOT NULL AND ")
        assert f"lon BETWEEN {dates.AMERICAS_LON_MIN} AND {dates.AMERICAS_LON_MAX}" in sql
        assert (
            f"THEN {dates.DATE_CUTOFF_AMERICAS} ELSE {dates.DATE_CUTOFF_REST_OF_WORLD} END" in sql
        )
        assert "period_end IS NOT NULL AND period_end <> 0 THEN period_end" in sql
        assert L.outside_e3_window("u.").startswith("(u.lon IS NOT NULL AND ")


class TestTheCells:
    def test_every_decision_fills_both_columns_from_null(self) -> None:
        result = build(export(site(FORT)), {FORT: finding(FORT, S.OUT_OF_WINDOW, WINDOW_NOTE)})
        cells = {(c.column, c.old_value, c.new_value) for c in result.plan.changes}
        assert cells == {
            ("scope_status", None, "retired"),
            ("scope_reason", None, result.decisions[0].reason),
        }
        assert {c.premise for c in result.plan.changes} == {f"premise-{FORT[:8]}"}

    def test_a_site_already_assessed_is_left_alone(self) -> None:
        assessed = site(FORT, scope_status="in_scope", scope_reason="kept")
        result = build(export(assessed), {FORT: finding(FORT, S.OUT_OF_WINDOW, WINDOW_NOTE)})
        assert not result.decisions and result.refused[0][1] == "already-assessed"

    def test_the_plan_validates_and_renders_on_the_lane(self, tmp_path: Path) -> None:
        result = build(export(site(FORT)), {FORT: finding(FORT, S.OUT_OF_WINDOW, WINDOW_NOTE)})
        plan_path = tmp_path / "PLAN.jsonl"
        P.write_plan_jsonl(result.plan, plan_path)
        P.write_rollback_sql(result.plan, tmp_path / "ROLLBACK.sql", plan_path=plan_path)
        records = A.load_records(plan_path)
        A.validate_records(records, lane=L.SCOPE)
        A.emit(records, tmp_path, L.SCOPE, plan_path=plan_path)
        undo = (tmp_path / "ROLLBACK.sql").read_text(encoding="utf-8")
        assert f"'{FORT}'::uuid, 'scope_status', 'retired', NULL," in undo


class TestTheDecisionsFile:
    def write(self, tmp_path: Path, entries: list[dict[str, Any]]) -> Path:
        path = tmp_path / "DECISIONS.json"
        path.write_text(json.dumps({"decisions": entries}), encoding="utf-8")
        return path

    def entry(self, **over: Any) -> dict[str, Any]:
        base = {
            "site_id": FORT,
            "name": "a",
            "rule": "a",
            "status": "pending",
            "quote": "q",
            "note": "n",
        }
        base.update(over)
        return base

    def test_a_site_decided_twice_is_refused(self, tmp_path: Path) -> None:
        with pytest.raises(P.PlanError, match="decided twice"):
            S.load_decisions(self.write(tmp_path, [self.entry(), self.entry()]))

    @pytest.mark.parametrize(
        ("over", "message"),
        [
            ({"status": "hidden"}, "rule 'a' / 'hidden'"),
            ({"rule": "e"}, "rule 'e'"),
            ({"quote": ""}, "needs a quote and a note"),
            ({"site_id": "not-a-uuid"}, "is not a UUID"),
        ],
    )
    def test_a_malformed_entry_is_refused(self, tmp_path: Path, over: dict, message: str) -> None:
        with pytest.raises(P.PlanError, match=message):
            S.load_decisions(self.write(tmp_path, [self.entry(**over)]))


class TestTheDeliveredPlan:
    DIR = A.lane_dir(L.SCOPE)

    def test_the_delivered_plan_validates_on_the_lane(self) -> None:
        records = A.load_records(self.DIR / "PLAN.jsonl")
        A.validate_records(records, lane=L.SCOPE)
        assert len(records) % 2 == 0
        statuses = [r.new_value for r in records if r.column == "scope_status"]
        assert set(statuses) <= set(L.SCOPE.cell("scope_status").allowed_new_values)

    def test_every_planned_site_is_in_the_review(self) -> None:
        review = (self.DIR / "REVIEW.md").read_text(encoding="utf-8")
        for r in A.load_records(self.DIR / "PLAN.jsonl"):
            assert f"`{r.site_id}`" in review

    def test_every_reviewed_decision_is_loadable(self) -> None:
        decisions = S.load_decisions(self.DIR / "DECISIONS.json")
        assert all(d.quote for d in decisions.values())


@needs_t11
def test_t11_runs_over_an_export_and_names_each_kind_this_lane_decides() -> None:
    rows = [
        site(FORT),
        site(UNDATED, period_start=None, period_name=None),
        site(MUSEUM, site_type="Museum", period_start=1903, lat=38.48, lon=22.5),
        site(GATE, period_start=-500, lat=31.78, lon=35.23),
    ]
    got = S.t11_findings(rows, REPO / "output" / "remediation" / "cache")
    assert {k: v.test_id for k, v in got.items()} == {
        FORT: S.OUT_OF_WINDOW,
        UNDATED: S.UNDATED,
        MUSEUM: S.MUSEUM,
    }
