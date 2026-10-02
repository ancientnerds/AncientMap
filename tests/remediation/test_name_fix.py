"""Two renames of 2026-10-01 (lane `name-fix`): does each site get exactly its own Wikipedia title?

`mechanical/name_fix.py` plans "Temple of Augustus, Split" -> "Temple of Augustus, Pula" and
"Gate of All Nations<U+200C> Persepolis" -> "Gate of All Nations": the name and its Postgres-computed
key of two curated rows, each new name the site's own `enwiki_title`. DB-less: production is a fixture
read; each plan-side check refuses on its own; the delivered plan is re-derived from the delivered
read and compared with the committed files.
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[2]
if str(REPO / "scripts" / "remediation") not in sys.path:
    sys.path.insert(0, str(REPO / "scripts" / "remediation"))

from mechanical import apply as A  # noqa: E402
from mechanical import lane as L  # noqa: E402
from mechanical import name_fix as N  # noqa: E402
from mechanical import plan as P  # noqa: E402

from tests.remediation.test_mechanical import FOREIGN, ProbeProduction  # noqa: E402

PULA, GATE = N.RENAMES
SPLIT_ID, GATE_ID = PULA.site_id, GATE.site_id
ZWNJ = "\u200c"
DELIVERED = REPO / "output" / "remediation" / "mechanical_name_fix"
NOW = "2026-10-01T00:00:00+00:00"
needs_plan = pytest.mark.skipif(
    not (DELIVERED / "PLAN.jsonl").exists(), reason=f"{DELIVERED} not built yet"
)


def site_row(rename: N.Rename, key: str, qid: str, **over: Any) -> dict[str, Any]:
    row = {
        "id": rename.site_id, "name": rename.old, "name_hex": rename.old.encode().hex(),
        "name_normalized": key, "source_id": "ancient_nerds", "scope_status": None,
        "premise": f"enwiki_title={rename.new}, wikidata_qid={qid}",
    }  # fmt: skip
    return {**row, **over}


def a_read(**over: Any) -> N.Read:
    base = N.Read(
        sites={
            SPLIT_ID: site_row(PULA, "temple of augustus, split", "Q770030"),
            GATE_ID: site_row(GATE, f"gate of all nations{ZWNJ} persepolis", "Q5527015"),
        },
        ext={
            SPLIT_ID: (("enwiki_title", PULA.new), ("wikidata_qid", "Q770030")),
            GATE_ID: (("enwiki_title", GATE.new), ("wikidata_qid", "Q5527015")),
        },
        keys={PULA.new: "temple of augustus, pula", GATE.new: "gate of all nations"},
        holders=(),
        journal={},
        stamps={},
        read_at="2026-10-01 09:52:57+00",
    )
    return replace(base, **over)


def with_site(site_id: str, **row: Any) -> N.Read:
    read = a_read()
    return a_read(sites={**read.sites, site_id: {**read.sites[site_id], **row}})


def refuses(read: N.Read, message: str) -> None:
    with pytest.raises(P.PlanError, match=message):
        N.build(read, NOW)


# ------------------------------------------------------------------------------ the decision
class TestTheDecision:
    def test_the_two_renames_as_decided(self) -> None:
        assert (PULA.site_id, PULA.old, PULA.new) == (
            "4a07cc38-1b55-4254-b0ad-fe875310caf7",
            "Temple of Augustus, Split",
            "Temple of Augustus, Pula",
        )
        assert (GATE.site_id, GATE.old, GATE.new) == (
            "f9cfc5f7-a6c8-4c6f-9d82-f30151a36d6c",
            f"Gate of All Nations{ZWNJ} Persepolis",
            "Gate of All Nations",
        )

    def test_the_plan_is_four_cells_with_the_key_of_the_new_name(self) -> None:
        plan = N.build(a_read(), NOW)
        assert plan.lane is L.NAME_FIX and plan.counters == {"sites": 2, "cells": 4}
        assert [(v.site_id, v.column, v.old_value, v.new_value) for v in plan.changes] == [
            (SPLIT_ID, "name", PULA.old, PULA.new),
            (SPLIT_ID, "name_normalized", "temple of augustus, split", "temple of augustus, pula"),
            (GATE_ID, "name", GATE.old, GATE.new),
            (GATE_ID, "name_normalized", f"gate of all nations{ZWNJ} persepolis", "gate of all nations"),
        ]  # fmt: skip
        assert {v.premise for v in plan.changes if v.site_id == SPLIT_ID} == {
            "enwiki_title=Temple of Augustus, Pula, wikidata_qid=Q770030"
        }

    def test_the_new_names_hold_no_zero_width_character_and_the_old_one_does(self) -> None:
        assert N.ZERO_WIDTH.search(GATE.old) and not N.ZERO_WIDTH.search(GATE.new)
        assert not N.ZERO_WIDTH.search(PULA.old) and not N.ZERO_WIDTH.search(PULA.new)

    def test_the_sql_and_the_python_class_name_the_same_characters(self) -> None:
        """`lane.ZERO_WIDTH_NAME` (Postgres' `\\u` regex escapes) and `name_fix.ZERO_WIDTH` agree."""
        body = re.search(r"\[(.*)\]", L.ZERO_WIDTH_NAME)
        assert body is not None
        sql_class = re.compile(f"[{body.group(1)}]")
        for char in ("\u200b", "\u200c", "\u200d", "\u200e", "\u200f", "\u2060", "\ufeff"):
            assert sql_class.match(char) and N.ZERO_WIDTH.match(char), hex(ord(char))
        for char in ("a", " ", "\u2010", "\u2061", "\u00a0", "\ufefe"):
            assert not sql_class.match(char) and not N.ZERO_WIDTH.match(char), hex(ord(char))

    def test_each_rename_carries_its_sources(self) -> None:
        for rename in N.RENAMES:
            assert rename.evidence and all(e["quote"] and e["url"] for e in rename.evidence)
            assert any("wikipedia.org" in e["url"] for e in rename.evidence)
            assert any("wikidata.org" in e["url"] for e in rename.evidence)
        plan = N.build(a_read(), NOW)
        for v in plan.changes:
            assert v.evidence[-1]["source"] == "production:unified_sites"

    @pytest.mark.parametrize(
        ("read", "message"),
        [
            (lambda: with_site(SPLIT_ID, source_id="wikidata"), "not a curated site"),
            (lambda: with_site(SPLIT_ID, scope_status="retired"), "the site is retired"),
            (lambda: with_site(SPLIT_ID, name_hex="00"), "the row holds"),
            (lambda: with_site(GATE_ID, name_hex=GATE.old.replace(ZWNJ, "").encode().hex()), "the row holds"),
            (lambda: with_site(SPLIT_ID, name_normalized=None), "no match key"),
            (lambda: a_read(sites={GATE_ID: a_read().sites[GATE_ID]}), "not in unified_sites"),
            (
                lambda: a_read(
                    journal={(SPLIT_ID, "name"): (P.JournalLink(9, "s", "t", "a", "other"),)}
                ),
                "journal-disagrees",
            ),
            (
                lambda: a_read(
                    journal={
                        (GATE_ID, "name_normalized"): (
                            P.JournalLink(9, "s", "t", None, "x"),
                            P.JournalLink(10, "s", "t", "y", f"gate of all nations{ZWNJ} persepolis"),
                        )
                    }
                ),
                "journal-chain-broken",
            ),
            (lambda: a_read(ext={**a_read().ext, SPLIT_ID: (("wikidata_qid", "Q770030"),)}), "its enwiki_title is"),
            (
                lambda: a_read(
                    ext={**a_read().ext, SPLIT_ID: (("enwiki_title", "Temple of Augustus"),)}
                ),
                "its enwiki_title is",
            ),
            (
                lambda: a_read(
                    ext={
                        **a_read().ext,
                        GATE_ID: (("enwiki_title", GATE.new), ("enwiki_title", "Another")),
                    }
                ),
                "its enwiki_title is",
            ),
            (lambda: with_site(SPLIT_ID, premise="wikidata_qid=Q770030"), "does not carry the title"),
            (lambda: a_read(keys={GATE.new: "gate of all nations"}), "no match key of the new name"),
            (
                lambda: a_read(
                    holders=(
                        {"id": "1" * 8, "name": PULA.new, "name_normalized": "temple of augustus, pula",
                         "scope_status": None},
                    )
                ),
                "two visible rows would be called",
            ),
            (lambda: a_read(stamps={L.NAME_FIX.run_stamp: 4}), "never re-planned"),
            (lambda: a_read(stamps={L.NAME_FIX.rollback_run_stamp: 1}), "never re-planned"),
        ],
        ids=[
            "not-curated", "retired", "name-hex-differs", "zero-width-already-gone",
            "no-key", "row-gone", "journal-disagrees", "journal-chain", "no-title", "other-title",
            "two-titles", "premise-without-title", "no-key-read", "another-visible-holder",
            "stamp-written", "rollback-stamp-written",
        ],
    )  # fmt: skip
    def test_each_check_refuses_on_its_own(self, read: Any, message: str) -> None:
        refuses(read(), message)

    def test_a_retired_or_own_holder_of_the_key_is_no_obstacle(self) -> None:
        holders = (
            {"id": SPLIT_ID, "name": PULA.new, "name_normalized": "temple of augustus, pula",
             "scope_status": None},
            {"id": "1" * 8, "name": PULA.new, "name_normalized": "temple of augustus, pula",
             "scope_status": "retired"},
            {"id": "2" * 8, "name": "Other", "name_normalized": "other", "scope_status": None},
        )  # fmt: skip
        assert N.build(a_read(holders=holders), NOW).counters["cells"] == 4

    def test_a_journal_that_ends_at_the_live_value_is_no_obstacle(self) -> None:
        journal = {(SPLIT_ID, "name"): (P.JournalLink(9, "s", "t", "x", PULA.old),)}
        assert N.build(a_read(journal=journal), NOW).counters["cells"] == 4

    def test_a_new_name_that_is_not_a_clean_name_is_refused(self) -> None:
        bad = replace(PULA, new="Temple of Augustus, Pula ")
        with pytest.raises(P.PlanError, match="not a name that fits"):
            N.check_rename(a_read(), bad)
        dirty = replace(PULA, new=f"Temple of Augustus,{ZWNJ} Pula")
        with pytest.raises(P.PlanError, match="zero-width"):
            N.check_rename(a_read(), dirty)
        long = replace(PULA, new="x" * 501)
        with pytest.raises(P.PlanError, match="not a name that fits"):
            N.check_rename(a_read(), long)


# ------------------------------------------------------------------------------ the read
class TestTheRead:
    def test_one_read_only_snapshot_of_exactly_the_two_rows(self) -> None:
        script = P.tagged_export_script(N.read_parts())
        assert "BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;" in script
        assert f"u.id IN ('{SPLIT_ID}', '{GATE_ID}')" in script
        assert L.NAME_FIX_PREMISE_SQL in script
        assert "VALUES ('Gate of All Nations'), ('Temple of Augustus, Pula')" in script
        assert "left(lower(unaccent(n)), 500)" in script
        for stamp in (L.NAME_FIX.run_stamp, L.NAME_FIX.rollback_run_stamp):
            assert f"'{stamp}'" in script
        assert not re.search(r"(?i)\b(insert|update|delete|truncate|drop)\b", script)

    def test_the_tagged_lines_become_the_read(self) -> None:
        read = a_read()
        lines = [
            *({"kind": "site", "row": row} for row in read.sites.values()),
            *(
                {"kind": "ext", "row": {"id": sid, "kind": k, "value": v}}
                for sid, pairs in read.ext.items()
                for k, v in pairs
            ),
            *({"kind": "key", "row": {"name": n, "key": k}} for n, k in read.keys.items()),
            {"kind": "journal", "row": {"id": 5, "row_pk": SPLIT_ID, "column_name": "name",
                                        "run_stamp": "s", "test_id": "t", "old_value": "a",
                                        "new_value": PULA.old}},
            {"kind": "stamp", "row": {"run_stamp": L.NAME_FIX.run_stamp, "n": 0}},
            {"kind": "snapshot", "row": {"exported_at": "2026-10-01 09:52:57+00"}},
        ]  # fmt: skip
        parsed = N.parse_read("".join(json.dumps(line) + "\n" for line in lines))
        assert set(parsed.sites) == {SPLIT_ID, GATE_ID} and parsed.keys == read.keys
        assert (
            parsed.ext == read.ext and parsed.journal[(SPLIT_ID, "name")][0].new_value == PULA.old
        )
        assert N.build(parsed, NOW).counters["cells"] == 4
        twice = "".join(json.dumps(line) + "\n" for line in [lines[-1], *lines])
        with pytest.raises(P.PlanError, match="one snapshot"):
            N.parse_read(twice)

    def test_the_files_are_the_lane_s_and_the_undo_is_pinned_to_the_plan(
        self, tmp_path: Path
    ) -> None:
        plan = N.build(a_read(), NOW)
        directory = N.write_plan(plan, a_read(), tmp_path)
        records = A.load_records(directory / "PLAN.jsonl")
        A.validate_records(records, lane=L.NAME_FIX)
        assert A.emit(records, directory, L.NAME_FIX, plan_path=directory / "PLAN.jsonl") == 4
        P.verify_pinned(
            directory / "ROLLBACK.sql",
            plan_path=directory / "PLAN.jsonl",
            expected=A.rollback_statement(records, L.NAME_FIX),
        )
        page = (directory / "PLAN.md").read_text(encoding="utf-8")
        assert "**2 sites, 4 cells.**" in page and "Gate of All Nations\\u200c Persepolis" in page
        assert "--lane name-fix --rehearse-rollback" in page

    def test_the_cli_refuses_without_writing_when_the_read_is_refused(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        read = with_site(SPLIT_ID, source_id="geonames")
        monkeypatch.setattr(N, "write_read", lambda path: path)
        monkeypatch.setattr(N, "parse_read", lambda _text: read)
        monkeypatch.setattr(Path, "read_text", lambda self, encoding=None: "")
        assert N.main(["--root", str(tmp_path), "--write"]) == 1
        assert (
            "REFUSED" in capsys.readouterr().err and not (tmp_path / "mechanical_name_fix").exists()
        )


# ------------------------------------------------------------------------------ the lane
class TestTheLane:
    def test_it_is_registered_with_its_own_stamp_directory_and_read_back(self) -> None:
        lane = L.NAME_FIX
        assert L.resolve_lane("name-fix") is lane and A.readback_for(lane) is L.NAME_FIX_READBACK
        assert lane.run_stamp == "2026-10-01_mechanical-name-fix" and lane.test_id == "B1/name-fix"
        assert lane.run_stamp not in (L.NAME_L5.run_stamp, L.CHIAPA_NAME.run_stamp)
        assert A.lane_dir(lane) == DELIVERED and lane.cells == L.NAME_CELLS
        assert (
            lane.write_invariant is L._NAME_KEY_DIFFERS
            and lane.premise_sql == L.NAME_FIX_PREMISE_SQL
        )

    def test_the_read_back_counts_the_defect_and_the_key_invariants(self) -> None:
        readback = L.NAME_FIX_READBACK
        assert "curated names holding a zero-width character" in readback
        assert L.ZERO_WIDTH_NAME in readback
        assert "curated rows whose name_normalized is not the key of their name" in readback
        assert "visible curated rows sharing their name key" in readback
        assert f"'{L.NAME_FIX.run_stamp}'" in readback

    def test_both_directions_carry_the_premise_and_the_key_invariant(self, tmp_path: Path) -> None:
        records = A.load_records(self._plan(tmp_path))
        for sql in (
            A.apply_statement(records, L.NAME_FIX),
            A.rollback_statement(records, L.NAME_FIX),
        ):
            assert f"WHERE ({L.NAME_FIX_PREMISE_SQL}) IS DISTINCT FROM p.premise;" in sql
            assert "invariant 3, the lane's own" in sql
            assert "'enwiki_title=Gate of All Nations, wikidata_qid=Q5527015'" in sql

    def test_every_guard_has_its_probe_and_each_is_refused_by_its_own(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        records = A.load_records(self._plan(tmp_path))
        cases = {c[0] for c in A.probe_cases(records, L.NAME_FIX, FOREIGN)}
        assert cases == {
            "guard1-other-source", "guard2-no-op", "guard2-foreign-column", "guard2-too-long",
            "guard3-foreign-old-value", "guard5-premise", "invariant-lane",
        }  # fmt: skip
        ProbeProduction(L.NAME_FIX, records, monkeypatch)
        assert A.cmd_probe_guards(records, tmp_path, L.NAME_FIX) == 0
        assert capsys.readouterr().out.count("refused by its own guard=True") == len(cases)

    @staticmethod
    def _plan(directory: Path) -> Path:
        P.write_plan_jsonl(N.build(a_read(), NOW), directory / "PLAN.jsonl")
        return directory / "PLAN.jsonl"


# ------------------------------------------------------------------------ the delivered plan
@needs_plan
class TestTheDeliveredPlan:
    def test_the_plan_is_what_the_delivered_read_decides(self) -> None:
        read = N.parse_read((DELIVERED / "READ.jsonl").read_text(encoding="utf-8"))
        plan = N.build(read, NOW)
        delivered = [
            json.loads(line)
            for line in (DELIVERED / "PLAN.jsonl").read_text(encoding="utf-8").splitlines()
        ]
        assert delivered == [P.plan_record(v, plan) for v in plan.changes]
        assert [(r["column"], r["new_value"]) for r in delivered] == [
            ("name", "Temple of Augustus, Pula"),
            ("name_normalized", "temple of augustus, pula"),
            ("name", "Gate of All Nations"),
            ("name_normalized", "gate of all nations"),
        ]

    def test_the_read_found_the_old_names_byte_for_byte(self) -> None:
        read = N.parse_read((DELIVERED / "READ.jsonl").read_text(encoding="utf-8"))
        assert read.sites[GATE_ID]["name_hex"] == (
            "47617465206f6620416c6c204e6174696f6e73e2808c205065727365706f6c6973"
        )
        assert read.sites[SPLIT_ID]["name"] == "Temple of Augustus, Split"
        assert read.stamps == {} and read.holders == ()

    def test_the_committed_statements_are_the_plan_s_own(self) -> None:
        records = A.load_records(DELIVERED / "PLAN.jsonl")
        A.validate_records(records, lane=L.NAME_FIX)
        P.verify_pinned(
            DELIVERED / "APPLY.sql",
            plan_path=DELIVERED / "PLAN.jsonl",
            expected=A.apply_statement(records, L.NAME_FIX),
        )
        P.verify_pinned(
            DELIVERED / "ROLLBACK.sql",
            plan_path=DELIVERED / "PLAN.jsonl",
            expected=A.rollback_statement(records, L.NAME_FIX),
        )
