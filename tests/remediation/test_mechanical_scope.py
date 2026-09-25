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
    listed: tuple[S.ListedDuplicate, ...] = (),
    held: frozenset[str] = frozenset(),
) -> S.ScopePlan:
    return S.build_scope_plan(
        ex, findings, decisions or {}, entities or {}, listed=listed, held=held, built_at="t"
    )


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

    def test_an_undated_museum_without_a_decision_is_refused_not_pending(self) -> None:
        """Audit 2026-09-25 m11: the module docstring's rule (d) needs a reviewed decision for
        every Museum row, the undated ones included; one without was planned `pending`."""
        museum = site(UNDATED, site_type="Museum", period_start=None, description="Roman finds.")
        findings = {UNDATED: finding(UNDATED, S.UNDATED, "no date")}
        result = build(export(museum), findings)
        assert not result.decisions
        assert [(r[0]["id"], r[1]) for r in result.refused] == [
            (UNDATED, "museum-needs-a-decision")
        ]

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


OTHER = "4a9b3802-1067-4f6b-a144-4c2ffe9619a4"
BANIAS = "ae2ca7b1-89da-46cb-8924-f9d04dd5da2e"
CAESAREA = "ce7db300-8777-425d-917a-2f6d9f325b58"


def listed(loser: str, survivor: str, qid: str = "Q1242421") -> S.ListedDuplicate:
    """A `DUPLICATES.jsonl` line as `bcases/classify.py` writes it."""
    return S.ListedDuplicate(
        loser=loser,
        survivor=survivor,
        evidence=(
            {
                "source": "production:site_external_ids",
                "url": f"https://www.wikidata.org/wiki/{qid}",
                "quote": f"both rows carry {qid}; 'x' and 'y' are both names of it; 7.0 m apart",
            },
            {"source": "survivor rule", "url": None, "quote": "survives by more content links"},
        ),
    )


def item(qid: str = "Q1242421") -> dict[str, str]:
    return {"wikidata_qid": qid}


class TestTheListedDuplicates:
    """`bcases/DUPLICATES.jsonl` retires its losers too - re-read in the export, one retirement per
    loser whoever found it, and never a pair held for the owner."""

    NAMES = {"Q1242421": entity("Dooey's Cairn", "Ballymacaldrack Court Tomb", "x")}

    def sites(self) -> tuple[dict[str, Any], dict[str, Any]]:
        a, b = TestRuleC().sites()
        return {**a, "ext": item()}, {**b, "ext": item()}

    def test_a_listed_loser_is_retired_as_a_duplicate_of_its_survivor(self) -> None:
        """A pair the lane's own 100 m rule does not see (no pair in the export) is retired on the
        list alone, with the list's evidence and today's reading of it."""
        a, b = self.sites()
        b = {**b, "lat": b["lat"] + 0.0001}  # 11.1 m north
        result = build(export(a, b), {}, listed=(listed(DUP_B, DUP_A),))
        (d,) = result.decisions
        assert (d.site["id"], d.rule, d.status, d.reason) == (
            DUP_B,
            "c",
            "retired",
            f"duplicate_of:{DUP_A}",
        )
        sources = [e["source"] for e in d.evidence]
        assert sources == [
            "bcases:DUPLICATES.jsonl",
            "production:site_external_ids",
            "survivor rule",
        ]
        assert d.evidence[0]["quote"].endswith("both rows carry Q1242421, 11.1 m apart")
        assert d.evidence[2]["url"] == S.LISTED_URL
        assert (result.counters["duplicates_listed"], result.counters["duplicates"]) == (1, 1)

    def test_a_pair_found_and_listed_is_one_retirement_with_both_evidences(self) -> None:
        a, b = self.sites()
        result = build(
            export(a, b, pairs=(TestRuleC.PAIR,)),
            {},
            entities=self.NAMES,
            listed=(listed(DUP_B, DUP_A),),
        )
        assert [(d.site["id"], d.reason) for d in result.decisions] == [
            (DUP_B, f"duplicate_of:{DUP_A}")
        ]
        assert not result.refused
        sources = {e["source"] for e in result.decisions[0].evidence}
        assert {"wikidata:Q1242421", "bcases:DUPLICATES.jsonl", "survivor rule"} <= sources
        assert result.counters["duplicates_found_and_listed"] == 1
        assert result.counters["duplicates"] == 1 and result.counters["cells"] == 2

    def test_a_loser_the_two_name_with_different_survivors_is_refused(self) -> None:
        a, b = self.sites()
        third = site(OTHER, name="Ballymacaldrack", ext=item())
        result = build(
            export(a, b, third, pairs=(TestRuleC.PAIR,)),
            {},
            entities=self.NAMES,
            listed=(listed(DUP_B, OTHER),),
        )
        assert not result.decisions
        assert [(r[0]["id"], r[1]) for r in result.refused] == [(DUP_B, "survivors-disagree")]

    @pytest.mark.parametrize("found", [True, False])
    def test_a_pair_held_for_the_owner_is_never_retired(self, found: bool) -> None:
        """Banias / Caesarea Philippi (B10) stays out whoever finds the pair: the list, or this
        lane's own rule should the two rows ever lie within 100 m."""
        banias = site(BANIAS, name="Banias", ext=item("Q606295"))
        caesarea = site(CAESAREA, name="Caesarea Philippi", ext=item("Q606295"), links=5)
        pair = {"a": BANIAS, "b": CAESAREA, "qid": "Q606295", "metres": 89.5}
        result = build(
            export(banias, caesarea, pairs=(pair,) if found else ()),
            {},
            entities={"Q606295": entity("Banias", "Caesarea Philippi", "Banias")},
            listed=() if found else (listed(BANIAS, CAESAREA, "Q606295"),),
            held=frozenset({BANIAS, CAESAREA}),
        )
        assert not result.decisions
        assert [(r[0]["id"], r[1]) for r in result.refused] == [(BANIAS, "held-for-the-owner")]

    @pytest.mark.parametrize(
        ("loser_item", "claimed"),
        [("Q9", "Q1242421"), ("Q1242421", "Q9"), (None, "Q1242421")],
    )
    def test_a_listed_pair_that_no_longer_shares_its_item_is_refused(
        self, loser_item: str | None, claimed: str
    ) -> None:
        """The item waves of 2026-09-23 rewrote site_external_ids after the list was read."""
        a, b = self.sites()
        b = {**b, "ext": None if loser_item is None else item(loser_item)}
        result = build(export(a, b), {}, listed=(listed(DUP_B, DUP_A, claimed),))
        assert not result.decisions
        assert [(r[0]["id"], r[1]) for r in result.refused] == [(DUP_B, "listed-item-moved")]

    def test_a_listed_pair_now_further_apart_than_the_list_allows_is_refused(self) -> None:
        """The coordinate wave of 2026-09-23 moved points after the list was read."""
        a, b = self.sites()
        moved = {**b, "lat": b["lat"] + 0.05}
        result = build(export(a, moved), {}, listed=(listed(DUP_B, DUP_A),))
        assert not result.decisions
        ((row, why, note),) = result.refused
        assert (row["id"], why) == (DUP_B, "listed-pair-too-far") and "2000 m" in note

    def test_a_listed_site_that_is_not_curated_is_refused(self) -> None:
        a, _ = self.sites()
        with pytest.raises(P.PlanError, match=f"names {DUP_B}, which is not a curated site"):
            build(export(a), {}, listed=(listed(DUP_B, DUP_A),))


class TestTheDuplicateFiles:
    def write(self, tmp_path: Path, lines: list[dict[str, Any]], name: str) -> Path:
        path = tmp_path / name
        path.write_text("\n".join(json.dumps(line) for line in lines), encoding="utf-8")
        return path

    def line(self, **over: Any) -> dict[str, Any]:
        base = {
            "loser_id": DUP_B,
            "survivor_id": DUP_A,
            "evidence": [{"source": "s", "url": None, "quote": "q"}],
        }
        base.update(over)
        return base

    def test_the_list_reads_each_loser_its_survivor_and_the_evidence(self, tmp_path: Path) -> None:
        (got,) = S.load_listed_duplicates(self.write(tmp_path, [self.line()], "D.jsonl"))
        assert (got.loser, got.survivor, got.evidence[0]["quote"]) == (DUP_B, DUP_A, "q")

    @pytest.mark.parametrize(
        ("lines", "message"),
        [
            ([{"loser_id": "x"}], "'x' is not a UUID"),
            ([{"survivor_id": DUP_B}], "needs another row as survivor"),
            ([{"evidence": []}], "needs another row as survivor and evidence"),
            ([{}, {"survivor_id": OTHER}], "as a loser more than once"),
        ],
    )
    def test_a_malformed_list_is_refused(
        self, tmp_path: Path, lines: list[dict[str, Any]], message: str
    ) -> None:
        path = self.write(tmp_path, [self.line(**over) for over in lines], "D.jsonl")
        with pytest.raises(P.PlanError, match=message):
            S.load_listed_duplicates(path)

    def test_a_missing_list_is_refused(self, tmp_path: Path) -> None:
        with pytest.raises(P.PlanError, match="the owner-case duplicate list is part of the plan"):
            S.load_listed_duplicates(tmp_path / "DUPLICATES.jsonl")

    def test_the_held_file_names_every_site_of_its_groups(self, tmp_path: Path) -> None:
        path = self.write(tmp_path, [{"site_ids": [BANIAS, CAESAREA]}], "H.jsonl")
        assert S.load_held_sites(path) == frozenset({BANIAS, CAESAREA})
        with pytest.raises(P.PlanError, match="'Banias' is not a UUID"):
            S.load_held_sites(self.write(tmp_path, [{"site_ids": ["Banias"]}], "H.jsonl"))
        with pytest.raises(P.PlanError, match="the pairs held for the owner are part of the plan"):
            S.load_held_sites(tmp_path / "missing.jsonl")

    def test_the_planner_reads_the_list_and_the_held_pairs(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """`scope.py --write` plans the listed losers and leaves the held pair alone."""
        a, b = TestTheListedDuplicates().sites()
        banias = site(BANIAS, name="Banias", ext=item("Q606295"))
        caesarea = site(CAESAREA, name="Caesarea Philippi", ext=item("Q606295"))
        export_dir = tmp_path / "export"
        export_dir.mkdir()
        rows = [{"kind": "site", "row": row} for row in (a, b, banias, caesarea)]
        rows.append({"kind": "snapshot", "row": {"exported_at": "t"}})
        (export_dir / "export.jsonl").write_text(
            "".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8"
        )
        (export_dir / "wikidata_names.json").write_text('{"entities": {}}', encoding="utf-8")
        (tmp_path / "DECISIONS.json").write_text('{"decisions": []}', encoding="utf-8")
        lines = [
            {"loser_id": line.loser, "survivor_id": line.survivor, "evidence": line.evidence}
            for line in (listed(DUP_B, DUP_A), listed(BANIAS, CAESAREA, "Q606295"))
        ]
        monkeypatch.setattr(S, "DUPLICATES_LIST", self.write(tmp_path, lines, "D.jsonl"))
        monkeypatch.setattr(
            S,
            "DUPLICATES_HELD",
            self.write(tmp_path, [{"site_ids": [BANIAS, CAESAREA]}], "H.jsonl"),
        )
        monkeypatch.setattr(S, "t11_findings", lambda sites, cache: {})
        assert S.main(["--out", str(tmp_path), "--write"]) == 0
        records = A.load_records(tmp_path / "PLAN.jsonl")
        assert {(r.site_id, r.column, r.new_value) for r in records} == {
            (DUP_B, "scope_status", "retired"),
            (DUP_B, "scope_reason", f"duplicate_of:{DUP_A}"),
        }
        skipped = (tmp_path / "SKIPPED.jsonl").read_text(encoding="utf-8")
        assert "held-for-the-owner" in skipped and BANIAS in skipped

    def test_the_delivered_list_is_19_losers_and_the_held_pair_is_not_among_them(self) -> None:
        losers = S.load_listed_duplicates(S.DUPLICATES_LIST)
        held = S.load_held_sites(S.DUPLICATES_HELD)
        assert len(losers) == 19 and held == {BANIAS, CAESAREA}
        assert not {d.loser for d in losers} & held
        assert not {d.survivor for d in losers} & held


class TestTheRefusals:
    """Each refusal the review of 2026-09-23 found without a test: removing its guard turns the
    test red (`mechanical/mutation_sweep.py "scope:"`)."""

    def test_a_t11_kind_this_lane_does_not_decide_is_refused(self) -> None:
        """Without the refusal an unknown kind fell through to rule (b) and became `pending` with
        a reason ('no date') that is false for a dated row - and every SQL guard accepts it."""
        result = build(
            export(site(FORT)), {FORT: finding(FORT, "T11/ambiguous-region", "two regions")}
        )
        assert not result.decisions
        assert [(r[0]["id"], r[1]) for r in result.refused] == [(FORT, "t11-kind-not-decided-here")]

    def test_an_undated_row_cannot_be_kept_in_scope_by_rule_b(self) -> None:
        undated = site(UNDATED, period_start=None, description="A sanctuary notified in 1974.")
        keep = {UNDATED: decision(UNDATED, "a site", "b", "in_scope", "notified in 1974")}
        result = build(export(undated), {UNDATED: finding(UNDATED, S.UNDATED, "no date")}, keep)
        assert not result.decisions and result.refused[0][1] == "decision-not-allowed"

    def test_a_duplicate_loser_another_rule_decided_is_refused(self) -> None:
        a, b = TestRuleC().sites()
        names = {"Q1242421": entity("Dooey's Cairn", "Ballymacaldrack Court Tomb", "x")}
        result = build(
            export(a, b, pairs=(TestRuleC.PAIR,)),
            {DUP_B: finding(DUP_B, S.OUT_OF_WINDOW, WINDOW_NOTE)},
            entities=names,
        )
        assert [(d.site["id"], d.rule) for d in result.decisions] == [(DUP_B, "a")]
        assert (DUP_B, "two-decisions") in {(r[0]["id"], r[1]) for r in result.refused}

    def test_a_duplicate_chain_never_retires_a_survivor(self) -> None:
        """NEW loses to MID, MID loses to OLD, in that order: MID must not be retired while NEW
        names it as its survivor (the read-back's 'survivor is retired' invariant)."""
        old, mid, new = DUP_A, DUP_B, UNDATED
        rows = (
            site(old, name="Tomb", created_at="2026-01-01 00:00:00"),
            site(mid, name="Cairn", created_at="2026-02-01 00:00:00"),
            site(new, name="Court tomb", created_at="2026-03-01 00:00:00"),
        )
        pairs = (
            {"a": mid, "b": new, "qid": "Q1", "metres": 5.0},
            {"a": old, "b": mid, "qid": "Q1", "metres": 5.0},
        )
        result = build(
            export(*rows, pairs=pairs), {}, entities={"Q1": entity("Tomb", "Cairn", "Court tomb")}
        )
        assert [(d.site["id"], d.reason) for d in result.decisions] == [
            (new, f"duplicate_of:{mid}")
        ]
        assert (mid, "two-decisions") in {(r[0]["id"], r[1]) for r in result.refused}

    @pytest.mark.parametrize("reverse", [False, True], ids=["in-order", "reversed"])
    def test_a_loser_found_with_two_survivors_is_refused_in_any_pair_order(
        self, reverse: bool
    ) -> None:
        """Audit 2026-09-25 M8: a loser the lane's own rule finds with two survivors kept whichever
        pair came last, so the outcome depended on pair order. Which row stays is then a question:
        refused as `survivors-disagree`, like a found-vs-listed conflict."""
        first, second, loser = DUP_A, DUP_B, UNDATED
        rows = (
            site(first, name="Tomb", created_at="2026-01-01 00:00:00"),
            site(second, name="Cairn", created_at="2026-01-02 00:00:00"),
            site(loser, name="Court tomb", created_at="2026-03-01 00:00:00"),
        )
        pairs = (
            {"a": first, "b": loser, "qid": "Q1", "metres": 5.0},
            {"a": second, "b": loser, "qid": "Q1", "metres": 5.0},
        )
        result = build(
            export(*rows, pairs=pairs[::-1] if reverse else pairs),
            {},
            entities={"Q1": entity("Tomb", "Cairn", "Court tomb")},
        )
        assert not result.decisions
        assert [(r[0]["id"], r[1]) for r in result.refused] == [(loser, "survivors-disagree")]

    def test_t11_reporting_a_site_twice_is_refused(self) -> None:
        once = S.index_findings([finding(FORT, S.OUT_OF_WINDOW, "x")])
        assert set(once) == {FORT}
        with pytest.raises(P.PlanError, match="T11 reported .* twice"):
            S.index_findings([finding(FORT, S.OUT_OF_WINDOW, "x"), finding(FORT, S.UNDATED, "y")])

    def test_a_pair_whose_item_was_not_collected_is_refused(self) -> None:
        a, b = TestRuleC().sites()
        with pytest.raises(P.PlanError, match="Q1242421 was not collected - run --collect"):
            build(export(a, b, pairs=(TestRuleC.PAIR,)), {}, entities={})

    def test_wikidata_answering_no_entity_is_refused(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        def get_json(endpoint: str, params: dict[str, str], *, timeout: int = 60) -> dict:
            assert endpoint == P.WIKIDATA_API and params["action"] == "wbgetentities"
            assert params["ids"] == "Q1|Q2"
            return {"entities": {"Q1": entity("Tomb", "Tomb")}}

        monkeypatch.setattr(S, "get_json", get_json)
        path = tmp_path / "wikidata_names.json"
        with pytest.raises(P.PlanError, match=r"Wikidata answered no entity for \['Q2'\]"):
            S.collect_names([{"qid": "Q2"}, {"qid": "Q1"}], path)
        assert not path.exists()

    def test_a_decision_for_a_site_that_is_not_curated_is_refused(self) -> None:
        with pytest.raises(P.PlanError, match="which is not a curated site"):
            build(
                export(site(FORT)),
                {},
                {GATE: decision(GATE, "Damascus Gate", "a", "pending", "A Roman gate")},
            )

    def test_a_missing_decisions_file_is_refused(self, tmp_path: Path) -> None:
        with pytest.raises(P.PlanError, match="the reviewed decisions are part of the plan"):
            S.load_decisions(tmp_path / "DECISIONS.json")


class TestTheExport:
    SNAPSHOT = '{"kind": "snapshot", "row": {"exported_at": "t"}}\n'
    SITE = '{"kind": "site", "row": {"id": "x"}}\n'

    def test_an_export_is_its_one_snapshot_and_at_least_one_site(self) -> None:
        got = S.parse_export(self.SITE + '{"kind": "pair", "row": {"a": 1}}\n' + self.SNAPSHOT)
        assert (got.sites, got.pairs, got.journal, got.exported_at) == (
            ({"id": "x"},),
            ({"a": 1},),
            (),
            "t",
        )
        with pytest.raises(P.PlanError, match="one snapshot line, it has 0"):
            S.parse_export(self.SITE)
        with pytest.raises(P.PlanError, match="one snapshot line, it has 2"):
            S.parse_export(self.SITE + self.SNAPSHOT + self.SNAPSHOT)
        with pytest.raises(P.PlanError, match="no curated site"):
            S.parse_export(self.SNAPSHOT)
        with pytest.raises(P.PlanError, match="kind 'oops'"):
            S.parse_export(self.SITE + self.SNAPSHOT + '{"kind": "oops", "row": {}}\n')

    def test_the_premise_holds_the_description_a_quote_rests_on(self) -> None:
        """A reviewed decision quotes the description; if it changes between the export and the
        apply, guard 5 must refuse the site instead of journalling a quote the row lost."""
        assert L.SCOPE.premise_sql.endswith(", u.name, md5(coalesce(u.description, '')))")
        assert f"{L.SCOPE.premise_sql} AS premise" in S.EXPORT_SITES_SQL


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

    def test_every_listed_loser_is_retired_as_a_duplicate_of_its_listed_survivor(self) -> None:
        """The delivered plan carries the whole owner-case list, each loser once, and nothing of
        the pair held for the owner."""
        records = A.load_records(self.DIR / "PLAN.jsonl")
        reasons = {r.site_id: r.new_value for r in records if r.column == "scope_reason"}
        duplicates = {s: v for s, v in reasons.items() if str(v).startswith(S.DUPLICATE_PREFIX)}
        listed = {
            d.loser: f"{S.DUPLICATE_PREFIX}{d.survivor}"
            for d in S.load_listed_duplicates(S.DUPLICATES_LIST)
        }
        assert duplicates == listed
        assert not set(reasons) & S.load_held_sites(S.DUPLICATES_HELD)

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
