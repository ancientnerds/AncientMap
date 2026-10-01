"""Owner decision O9: do the five confirmed duplicates get exactly their retirement - and nothing else?

`mechanical/dups.py` plans one lane, `dup-retire`, from one read-only read: the loser of each of
five pairs (B1-D and B6 of the decisions file) gets `scope_status = 'retired'` and `scope_reason =
'duplicate_of:<survivor>'`, nothing else - no country (B10), no name, no description, no delete.
Each plan-side check refuses on its own here; the guards the transaction carries - the premise, the
three survivor checks at the lane's 2,000 m - are evaluated in SQLite where their SQL is portable,
and their probes are counted. The delivered-plan tests read `output/remediation/mechanical_dups/`.
"""

from __future__ import annotations

import json
import sqlite3
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[2]
if str(REPO / "scripts" / "remediation") not in sys.path:
    sys.path.insert(0, str(REPO / "scripts" / "remediation"))

from bcases.classify import DUP_MAX_M  # noqa: E402
from mechanical import apply as A  # noqa: E402
from mechanical import dups as D  # noqa: E402
from mechanical import lane as L  # noqa: E402
from mechanical import plan as P  # noqa: E402
from mechanical.scope import survivor_rank  # noqa: E402

from pipeline.utils.geo import haversine_distance  # noqa: E402
from tests.remediation.test_mechanical import FOREIGN, ProbeProduction  # noqa: E402
from tests.remediation.test_mechanical_chiapa import (  # noqa: E402
    HIDDEN_POINT,
    add,
    sqlite_sites,
)

CREATED = "2026-03-04 21:07:57.660461"
DELIVERED = REPO / "output" / "remediation" / "mechanical_dups"
DECISIONS = REPO / D.DECISIONS_FILE
needs_plan = pytest.mark.skipif(
    not (DELIVERED / "PLAN.jsonl").exists(), reason=f"{DELIVERED} not built yet"
)
NOW = "2026-10-01T00:00:00+00:00"

# What production held for the ten rows on 2026-10-01 (read-only): (links, images, citations) and
# the distance of the pair in metres.
FACTS = {
    "ae2ca7b1-89da-46cb-8924-f9d04dd5da2e": (4, 20, 1),  # Banias
    "ce7db300-8777-425d-917a-2f6d9f325b58": (5, 20, 3),  # Caesarea Philippi
    "3ebb514f-ac4a-4913-b54b-409bcc29eff4": (5, 17, 0),  # Ancient Amathunta
    "51daf6c9-25d3-4818-8857-0543f1203c57": (5, 17, 1),  # Amathus
    "dafc7527-c6c8-45c3-8c7d-4813d20a4dcf": (0, 20, 0),  # Ñusta Hispana
    "d41368ba-6aa2-4b75-adf4-8f2cd3cc7e4d": (0, 20, 0),  # Conjunto Arqueologico de Ñustahispana
    "f23a31c3-6833-4df6-8583-3b3930b5a74f": (0, 3, 0),  # Thirty-nine (39) Bridge Street
    "21ac323f-7214-4891-9499-74e55c3d7d56": (3, 3, 0),  # Bridge Street Number 39
    "f967e3c4-fc5b-4cd0-91d1-06030d51e31c": (0, 2, 0),  # Shaduppum
    "0d8af59c-71cb-4ff6-9620-3eb1faf2ebd3": (5, 2, 1),  # Tel Hermal Fort
}
METRES = {pair.loser: m for pair, m in zip(D.PAIRS, (289.5, 11.3, 468.1, 14.0, 20.3), strict=True)}
BANIAS, AMATHUNTA, NUSTA, BRIDGE, SHADUPPUM = D.PAIRS


def site_row(pair: D.Pair, site_id: str) -> dict[str, Any]:
    loser = site_id == pair.loser
    name = pair.loser_name if loser else pair.survivor_name
    links, images, citations = FACTS[site_id]
    return {
        "id": site_id, "name": name, "source_id": "ancient_nerds", "scope_status": None,
        "scope_reason": None, "lat": 1.0, "lon": 2.0, "created_at": CREATED, "links": links,
        "images": images, "citations": citations,
        "description": f"{pair.loser_quote if loser else pair.survivor_quote}. More text.",
        "premise": f"{name} | {D.ENWIKI}={pair.title}, {D.QID}={pair.qid}",
    }  # fmt: skip


def a_read(**over: Any) -> D.Read:
    sites: dict[str, Any] = {}
    ext: dict[str, tuple[tuple[str, str], ...]] = {}
    for pair in D.PAIRS:
        for site_id in (pair.loser, pair.survivor):
            sites[site_id] = site_row(pair, site_id)
            ext[site_id] = ((D.ENWIKI, pair.title), (D.QID, pair.qid))
    base = D.Read(
        sites=sites,
        ext=ext,
        metres=METRES,
        onto=(),
        journal={},
        stamps={},
        read_at="2026-10-01 14:58:15.479222+00",
    )
    return replace(base, **over)


def with_row(site_id: str, **over: Any) -> D.Read:
    read = a_read()
    return replace(read, sites={**read.sites, site_id: {**read.sites[site_id], **over}})


def without_row(site_id: str) -> D.Read:
    read = a_read()
    return replace(read, sites={k: v for k, v in read.sites.items() if k != site_id})


def with_ext(site_id: str, *pairs: tuple[str, str]) -> D.Read:
    read = a_read()
    return replace(read, ext={**read.ext, site_id: pairs})


# ------------------------------------------------------------------------------ the decision
class TestTheDecision:
    def test_the_five_pairs_as_decided(self) -> None:
        assert [(p.loser_name, p.survivor_name, p.decision) for p in D.PAIRS] == [
            ("Banias", "Caesarea Philippi", "B6"),
            ("Ancient Amathunta", "Amathus", "B1-D"),
            ("Ñusta Hispana", "Conjunto Arqueologico de Ñustahispana", "B1-D"),
            ("Thirty-nine (39) Bridge Street, Chester", "Bridge Street Number 39, Chester", "B1-D"),
            ("Shaduppum", "Tel Hermal Fort", "B1-D"),
        ]
        assert BANIAS.loser.startswith("ae2ca7b1") and BANIAS.survivor.startswith("ce7db300")
        assert BANIAS.reason == "duplicate_of:ce7db300-8777-425d-917a-2f6d9f325b58"
        ids = [i for p in D.PAIRS for i in (p.loser, p.survivor)]
        assert len(set(ids)) == 10 == len(FACTS)

    def test_the_survivor_is_the_scope_lane_s_rule_for_every_pair(self) -> None:
        read = a_read()
        for pair in D.PAIRS:
            ranked = sorted((read.sites[pair.loser], read.sites[pair.survivor]), key=survivor_rank)
            assert ranked[0]["id"] == pair.survivor, pair.loser_name

    def test_the_decision_quotes_are_the_decisions_file_s_words(self) -> None:
        text = " ".join(DECISIONS.read_text(encoding="utf-8").split())
        assert D.B1D_QUOTE in text and D.B6_QUOTE in text
        assert {p.decision_quote for p in D.PAIRS} == {D.B1D_QUOTE, D.B6_QUOTE}

    def test_every_pair_cites_wikipedia_and_wikidata_with_a_link(self) -> None:
        for pair in D.PAIRS:
            urls = [e["url"] for e in pair.evidence]
            assert all(u and u.startswith("https://") for u in urls), pair.loser_name
            assert any("wikipedia.org" in u for u in urls)
            assert any(f"wikidata.org/wiki/{pair.qid}" in u for u in urls)
            assert all(e["quote"] for e in pair.evidence)


# ------------------------------------------------------------------------------------ the plan
class TestThePlan:
    def test_the_plan_is_ten_cells_of_the_five_retired_rows(self) -> None:
        plan = D.build(a_read(), NOW)
        assert plan.lane is L.DUP_RETIRE and plan.counters == {"sites": 5, "cells": 10}
        assert [(v.site_id, v.column, v.old_value, v.new_value) for v in plan.changes] == [
            (p.loser, column, None, value)
            for p in D.PAIRS
            for column, value in (("scope_status", "retired"), ("scope_reason", p.reason))
        ]
        assert {v.column for v in plan.changes} == {"scope_status", "scope_reason"}  # no country
        for v in plan.changes:
            assert v.premise == a_read().sites[v.site_id]["premise"]
            assert v.finding_test_id == "O9/duplicate-retire" and v.rule == D.RULE

    def test_the_evidence_cites_the_decision_the_sources_and_the_survivor_rule(self) -> None:
        plan = D.build(a_read(), NOW)
        for v in plan.changes:
            sources = [e["source"] for e in v.evidence]
            assert D.DECISIONS_FILE in sources and "survivor rule" in sources
            assert any(s.startswith("en.wikipedia.org") for s in sources)
            assert any(s.startswith("wikidata:") for s in sources)
        banias = plan.changes[0].evidence
        assert banias[0]["quote"].startswith("B6: ")
        assert (
            "289.5 m apart"
            in [e for e in banias if e["source"].endswith("external_ids")][0]["quote"]
        )
        rule = banias[-1]
        assert "survivor 'Caesarea Philippi'" in rule["quote"] and "5 content link" in rule["quote"]

    @pytest.mark.parametrize(
        ("read", "message"),
        [
            (lambda: without_row(BANIAS.loser), "row to retire .* is not in unified_sites"),
            (lambda: with_row(BANIAS.loser, source_id="geonames"), "not a curated site"),
            (lambda: with_row(BANIAS.loser, name="Banias Caves"), "the decision names"),
            (
                lambda: with_row(BANIAS.loser, scope_status="pending", scope_reason="x"),
                "already has a scope decision",
            ),
            (
                lambda: with_row(BANIAS.loser, scope_reason="x"),
                "already has a scope decision",
            ),
            (
                lambda: a_read(
                    journal={
                        (BANIAS.loser, "scope_status"): (
                            P.JournalLink(9, "2026-09-25_x", "t", None, "retired"),
                        )
                    }
                ),
                "journal-disagrees",
            ),
            (lambda: without_row(BANIAS.survivor), "survivor .* is not in unified_sites"),
            (lambda: with_row(BANIAS.survivor, source_id="wikidata"), "not a curated site"),
            (lambda: with_row(BANIAS.survivor, name="Caesarea"), "the decision names"),
            (
                lambda: with_row(BANIAS.survivor, scope_status="retired", scope_reason="x"),
                "the survivor is retired",
            ),
            (
                lambda: a_read(onto=({"id": "1" * 8, "scope_reason": f"duplicate_of:{BANIAS.loser}"},)),
                "retired onto the row to retire already",
            ),
            (
                lambda: with_ext(BANIAS.loser, (D.ENWIKI, "Banias"), (D.QID, "Q1")),
                "wikidata_qid is",
            ),
            (lambda: with_ext(BANIAS.survivor, (D.QID, "Q606295")), "enwiki_title is"),
            (
                lambda: with_ext(
                    BANIAS.survivor, (D.ENWIKI, "Banias"), (D.ENWIKI, "Other"), (D.QID, "Q606295")
                ),
                "enwiki_title is",
            ),
            (
                lambda: with_row(BANIAS.loser, premise="Banias | "),
                "does not carry the ids",
            ),
            (lambda: a_read(metres={}), "no distance"),
            (lambda: a_read(metres={**METRES, BANIAS.loser: 2000.5}), "the lane allows 2000 m"),
            (
                lambda: with_row(BANIAS.survivor, created_at="2026-03-05 00:00:00"),
                "survivor rule keeps the row to retire",
            ),
            (
                lambda: with_row(NUSTA.loser, links=1),
                "survivor rule keeps the row to retire",
            ),
            (
                lambda: with_row(BANIAS.loser, description="Banias is a site."),
                "description does not hold",
            ),
            (
                lambda: with_row(SHADUPPUM.survivor, description="Tel Hermal is a fort."),
                "description does not hold",
            ),
            (
                lambda: a_read(stamps={L.DUP_RETIRE.run_stamp: 4}),
                "a lane that has written is never re-planned",
            ),
            (
                lambda: a_read(stamps={L.DUP_RETIRE.rollback_run_stamp: 1}),
                "a lane that has written is never re-planned",
            ),
        ],
        ids=[
            "loser-gone", "loser-not-curated", "loser-renamed", "loser-decided",
            "loser-reason-only", "loser-journal", "survivor-gone", "survivor-not-curated",
            "survivor-renamed", "survivor-retired", "retired-onto-loser", "loser-other-item",
            "survivor-no-title", "survivor-two-titles", "premise-without-ids", "no-distance",
            "too-far", "survivor-rule-age", "survivor-rule-links", "loser-description",
            "survivor-description", "stamp-written", "rollback-stamp-written",
        ],
    )  # fmt: skip
    def test_each_check_refuses_on_its_own(self, read: Any, message: str) -> None:
        with pytest.raises(P.PlanError, match=message):
            D.build(read(), NOW)

    def test_two_thousand_metres_is_the_limit_and_the_two_far_pairs_pass_it(self) -> None:
        assert L.DUP_RETIRE_METRES == 2000 == int(DUP_MAX_M)
        assert D.build(a_read(metres={**METRES, BANIAS.loser: 2000.0}), NOW).counters["sites"] == 5
        assert (
            METRES[BANIAS.loser] > L.DUPLICATE_METRES and METRES[NUSTA.loser] > L.DUPLICATE_METRES
        )

    def test_a_row_in_two_pairs_is_refused(self, monkeypatch: pytest.MonkeyPatch) -> None:
        chained = replace(AMATHUNTA, loser=BANIAS.survivor)
        monkeypatch.setattr(D, "PAIRS", (BANIAS, chained))
        with pytest.raises(P.PlanError, match="appears in two pairs"):
            D.build(a_read(), NOW)

    def test_a_journal_that_ends_at_the_live_value_is_no_obstacle(self) -> None:
        journal = {
            (BANIAS.loser, "scope_status"): (P.JournalLink(9, "2026-03-04_x", "t", "x", None),),
        }
        assert D.build(a_read(journal=journal), NOW).counters["cells"] == 10

    def test_a_pending_survivor_is_visible_and_no_obstacle(self) -> None:
        read = with_row(BANIAS.survivor, scope_status="pending", scope_reason="E3: held")
        assert D.build(read, NOW).counters["sites"] == 5


class TestTheRead:
    def test_one_read_only_snapshot_of_exactly_the_ten_rows(self) -> None:
        script = P.tagged_export_script(D.read_parts())
        assert "BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;" in script
        for site_id in FACTS:
            assert f"'{site_id}'" in script
        assert L.DUP_RETIRE_PREMISE_SQL in script
        for stamp in (L.DUP_RETIRE.run_stamp, L.DUP_RETIRE.rollback_run_stamp):
            assert f"'{stamp}'" in script
        for word in ("INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "TRUNCATE"):
            assert word not in script.upper().replace("DUPLICATE", "")

    def test_the_tagged_lines_become_the_read(self) -> None:
        read = a_read()
        lines: list[dict[str, Any]] = [
            *({"kind": "site", "row": row} for row in read.sites.values()),
            *(
                {"kind": "ext", "row": {"id": sid, "kind": kind, "value": value}}
                for sid, pairs in read.ext.items()
                for kind, value in pairs
            ),
            *({"kind": "metres", "row": {"loser": k, "metres": v}} for k, v in METRES.items()),
            {"kind": "onto", "row": {"id": "1" * 8, "name": "x", "scope_reason": "r"}},
            {
                "kind": "journal",
                "row": {
                    "id": 5,
                    "row_pk": BANIAS.loser,
                    "column_name": "scope_reason",
                    "run_stamp": "s",
                    "test_id": "t",
                    "old_value": None,
                    "new_value": None,
                },
            },  # fmt: skip
            {"kind": "stamp", "row": {"run_stamp": L.DUP_RETIRE.run_stamp, "n": 0}},
            {"kind": "snapshot", "row": {"exported_at": "2026-10-01 14:58:15+00"}},
        ]
        parsed = D.parse_read("".join(json.dumps(line) + "\n" for line in lines))
        assert set(parsed.sites) == set(FACTS) and parsed.metres == METRES
        assert parsed.ext[BANIAS.loser] == ((D.ENWIKI, "Banias"), (D.QID, "Q606295"))
        assert parsed.journal[(BANIAS.loser, "scope_reason")][0].id == 5
        assert parsed.read_at == "2026-10-01 14:58:15+00"
        assert D.build(replace(parsed, onto=()), NOW).counters["cells"] == 10
        with pytest.raises(P.PlanError, match="once|snapshot"):
            D.parse_read("".join(json.dumps(line) + "\n" for line in lines[:-1]))

    def test_the_files_are_the_mechanical_lane_s(self, tmp_path: Path) -> None:
        plan = D.build(a_read(), NOW)
        directory = D.write_plan(plan, a_read(), tmp_path)
        assert directory == tmp_path / "mechanical_dups"
        records = A.load_records(directory / "PLAN.jsonl")
        A.validate_records(records, lane=L.DUP_RETIRE)
        assert A.emit(records, directory, L.DUP_RETIRE, plan_path=directory / "PLAN.jsonl") == 10
        P.verify_pinned(
            directory / "ROLLBACK.sql",
            plan_path=directory / "PLAN.jsonl",
            expected=A.rollback_statement(records, L.DUP_RETIRE),
        )
        page = (directory / "PLAN.md").read_text(encoding="utf-8")
        assert "5 sites, 10 cells" in page and "no country is written (B10)" in page
        for pair in D.PAIRS:
            assert f"## {pair.loser_name} -> {pair.survivor_name} ({pair.decision})" in page


# ------------------------------------------------------------------------ the guards in SQL
needs_ordered_string_agg = pytest.mark.skipif(
    sqlite3.sqlite_version_info < (3, 44), reason="SQLite < 3.44 has no ORDER BY in aggregates"
)
SURVIVOR = "21ac323f-7214-4891-9499-74e55c3d7d56"
LOSER = "f23a31c3-6833-4df6-8583-3b3930b5a74f"
REASON = f"duplicate_of:{SURVIVOR}"


def north(metres: float) -> tuple[float, float]:
    """`HIDDEN_POINT` moved `metres` north (1 degree of latitude: 111.195 km on the haversine
    sphere)."""
    return (HIDDEN_POINT[0] + metres / 111195.0, HIDDEN_POINT[1])


def survivor_checks(db: sqlite3.Connection, lane: L.Lane) -> list[str]:
    return [
        invariant.probe_name
        for invariant in lane.site_invariants
        if db.execute(
            f"SELECT ({invariant.predicate}) FROM unified_sites u WHERE u.id = ?", (LOSER,)
        ).fetchone()[0]
    ]


class TestTheGuardsInSQL:
    @needs_ordered_string_agg
    def test_the_premise_is_the_name_and_the_external_ids(self) -> None:
        db = sqlite3.connect(":memory:")
        db.execute("CREATE TABLE unified_sites (id TEXT, name TEXT)")
        db.execute("CREATE TABLE site_external_ids (site_id TEXT, kind TEXT, value TEXT)")
        db.executemany(
            "INSERT INTO unified_sites VALUES (?, ?)", [("a", "Banias"), ("b", "Nothing")]
        )
        db.executemany(
            "INSERT INTO site_external_ids VALUES (?, ?, ?)",
            [("a", "wikidata_qid", "Q606295"), ("a", "enwiki_title", "Banias"), ("x", "k", "v")],
        )
        got = {
            site: db.execute(
                f"SELECT {L.DUP_RETIRE_PREMISE_SQL} FROM unified_sites u WHERE u.id = ?", (site,)
            ).fetchone()[0]
            for site in "ab"
        }
        assert got == {"a": "Banias | enwiki_title=Banias, wikidata_qid=Q606295", "b": "Nothing | "}

    @pytest.mark.parametrize(
        ("survivor", "fires"),
        [
            ({"metres": 11}, None),
            ({"metres": 289.5}, None),
            ({"metres": 1990}, None),
            ({"metres": 2012}, "survivor-far"),
            ({"metres": 5, "source": "geonames"}, "survivor-not-curated"),
            ({"metres": 5, "absent": True}, "survivor-not-curated"),
            ({"metres": 5, "status": "retired"}, "survivor-retired"),
            ({"metres": 5, "status": "pending"}, None),
            ({"metres": 5000, "status": "retired"}, "survivor-retired"),
        ],
        ids=[
            "11-m", "289-m", "1990-m", "2012-m", "not-curated", "no-such-row", "retired",
            "pending-is-visible", "far-and-retired",
        ],
    )  # fmt: skip
    def test_each_survivor_check_fires_for_its_kind_alone_at_2000_m(
        self, survivor: dict[str, Any], fires: str | None
    ) -> None:
        db = sqlite_sites()
        if not survivor.get("absent"):
            add(db, SURVIVOR, source=survivor.get("source", "ancient_nerds"),
                status=survivor.get("status"), point=north(survivor["metres"]))  # fmt: skip
        add(db, LOSER, status="retired", reason=REASON, point=HIDDEN_POINT)
        assert survivor_checks(db, L.DUP_RETIRE) == ([] if fires is None else [fires])

    def test_the_chiapa_hide_keeps_its_100_m(self) -> None:
        """The refactor that made the distance a parameter left the 100 m lanes as they were."""
        db = sqlite_sites()
        add(db, SURVIVOR, point=north(289.5))
        add(db, LOSER, status="retired", reason=REASON, point=HIDDEN_POINT)
        assert survivor_checks(db, L.CHIAPA_HIDE) == ["survivor-far"]
        assert survivor_checks(db, L.DUP_RETIRE) == []
        assert [i.says for i in L.CHIAPA_HIDE.site_invariants][-1].endswith("further than 100 m")
        assert L.CHIAPA_HIDE.site_invariants == L.DUPLICATE_SURVIVOR_INVARIANTS
        assert [i.says for i in L.DUP_RETIRE.site_invariants][-1].endswith("further than 2000 m")

    def test_the_two_edge_points_lie_either_side_of_2000_m(self) -> None:
        near, far = (north(m) for m in (1990, 2012))
        assert 1980 < 1000 * haversine_distance(*HIDDEN_POINT, *near) < 2000
        assert 2000 < 1000 * haversine_distance(*HIDDEN_POINT, *far) < 2020


# ------------------------------------------------------------------------------------ the lane
PROBES = {
    "guard1-other-source",
    "guard2-no-op",
    "guard2-foreign-column",
    "guard3-foreign-old-value",
    "guard4-not-owned",
    "guard5-premise",
    "invariant-survivor-not-curated",
    "invariant-survivor-retired",
    "invariant-survivor-far",
}


def lane_records(directory: Path) -> list[A.ChangeRecord]:
    """The records, written and read back as apply.py reads them."""
    P.write_plan_jsonl(D.build(a_read(), NOW), directory / "PLAN.jsonl")
    return A.load_records(directory / "PLAN.jsonl")


class TestTheLane:
    def test_the_lane_is_registered_with_its_own_directory_stamp_and_read_back(self) -> None:
        lane = L.DUP_RETIRE
        assert L.resolve_lane("dup-retire") is lane
        assert A.lane_dir(lane) == DELIVERED
        assert A.readback_for(lane) is L.DUP_RETIRE_READBACK
        taken = {other.run_stamp for other in L.LANES.values() if other is not lane}
        assert lane.run_stamp not in taken and lane.test_id != L.CHIAPA_HIDE.test_id
        assert lane.premise_sql == L.DUP_RETIRE_PREMISE_SQL
        assert [c.name for c in lane.cells] == ["scope_status", "scope_reason"]

    def test_the_lane_writes_retired_and_nothing_else(self, tmp_path: Path) -> None:
        assert L.DUP_RETIRE.cell("scope_status").allowed_new_values == ("retired",)
        records = lane_records(tmp_path)
        A.validate_records(records, lane=L.DUP_RETIRE)
        with pytest.raises(P.PlanError, match="not a value the dup-retire lane owns"):
            A.validate_records(
                [replace(records[0], new_value="in_scope"), *records[1:]], lane=L.DUP_RETIRE
            )
        with pytest.raises(ValueError, match="not a column this lane writes"):
            L.DUP_RETIRE.cell("country")

    def test_the_survivor_checks_run_after_the_write_and_only_on_it(self, tmp_path: Path) -> None:
        records = lane_records(tmp_path)
        write = A.apply_statement(records, L.DUP_RETIRE)
        loop = write.index("END LOOP;")
        checks = L.duplicate_survivor_invariants(L.DUP_RETIRE_METRES)
        assert L.DUP_RETIRE.site_invariants == checks and len(checks) == 3
        for invariant in checks:
            at = write.index(f"RAISE EXCEPTION 'O9 duplicate retirement: % {invariant.says}', bad;")
            assert at > loop
        assert f"WHERE ({L.DUP_RETIRE_PREMISE_SQL}) IS DISTINCT FROM p.premise;" in write
        undo = A.rollback_statement(records, L.DUP_RETIRE)
        assert "site invariant" not in undo
        assert f"WHERE ({L.DUP_RETIRE_PREMISE_SQL}) IS DISTINCT FROM p.premise;" in undo

    def test_every_guard_has_its_probe(self, tmp_path: Path) -> None:
        cases = {c[0]: c for c in A.probe_cases(lane_records(tmp_path), L.DUP_RETIRE, FOREIGN)}
        assert set(cases) == PROBES
        for invariant in L.DUP_RETIRE.site_invariants:
            _suffix, _name, mutated, says = cases[invariant.probe_suffix]
            assert says == invariant.says
            assert [r.new_value for r in mutated if r.column == "scope_reason"][0] == (
                invariant.probe_values[0]
            )

    def test_the_probes_pass_when_each_is_refused_by_its_own_guard(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
    ) -> None:
        records = lane_records(tmp_path)
        ProbeProduction(L.DUP_RETIRE, records, monkeypatch)
        assert A.cmd_probe_guards(records, tmp_path, L.DUP_RETIRE) == 0
        out = capsys.readouterr().out
        assert out.count("refused by its own guard=True") == len(PROBES)

    def test_the_read_back_counts_what_the_lane_moves(self) -> None:
        text = L.DUP_RETIRE_READBACK
        assert "curated rows retired as a duplicate'" in text
        assert "retired duplicates whose survivor is retired or not curated" in text
        assert "retired duplicates whose survivor lies further than 2000 m" in text
        assert f"'{L.DUP_RETIRE.run_stamp}'" in text and f"'{L.CHIAPA_HIDE.run_stamp}'" not in text


# ------------------------------------------------------------------------ the delivered plan
@needs_plan
class TestTheDeliveredPlan:
    def test_the_plan_is_the_five_retirements(self) -> None:
        records = A.load_records(DELIVERED / "PLAN.jsonl")
        A.validate_records(records, lane=L.DUP_RETIRE)
        assert [(r.site_id, r.column, r.old_value, r.new_value) for r in records] == [
            (p.loser, column, None, value)
            for p in D.PAIRS
            for column, value in (("scope_status", "retired"), ("scope_reason", p.reason))
        ]
        assert not any(r.column == "country" for r in records)

    def test_the_read_is_the_one_the_plan_rests_on(self) -> None:
        read = D.parse_read((DELIVERED / "READ.jsonl").read_text(encoding="utf-8"))
        plan = D.build(read, NOW)
        delivered = A.load_records(DELIVERED / "PLAN.jsonl")
        assert [(r.site_id, r.column, r.new_value, r.premise) for r in delivered] == [
            (v.site_id, v.column, v.new_value, v.premise) for v in plan.changes
        ]
        assert all(m <= L.DUP_RETIRE_METRES for m in read.metres.values())

    def test_the_undo_and_the_statement_are_the_ones_the_lane_renders(self) -> None:
        records = A.load_records(DELIVERED / "PLAN.jsonl")
        P.verify_pinned(
            DELIVERED / "ROLLBACK.sql",
            plan_path=DELIVERED / "PLAN.jsonl",
            expected=A.rollback_statement(records, L.DUP_RETIRE),
        )
        apply_sql = DELIVERED / "APPLY.sql"
        if apply_sql.exists():
            P.verify_pinned(
                apply_sql,
                plan_path=DELIVERED / "PLAN.jsonl",
                expected=A.apply_statement(records, L.DUP_RETIRE),
            )
