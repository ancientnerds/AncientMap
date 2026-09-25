"""Does the Phase-4/5 acceptance (WB-C3) refuse every write production does not account for?

`output/remediation/tools/verify_writes4.py` is what says a step of 100 sites may be followed by
the next. These tests give it a fake production that parses the SQL it is sent - it answers only
read-only SELECTs, reads the stamp patterns, the (table, column) pairs and the key lists out of the
statement, and computes the hash invariants the way Postgres would - and break one thing each: a
chain, a value, a quote, a stored text, a hash, a card file, a boot log. No socket, no production.
"""

from __future__ import annotations

import dataclasses
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[2]
TOOLS = REPO / "output" / "remediation" / "tools"
for path in (TOOLS, REPO / "scripts" / "remediation"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import lanes  # noqa: E402
import verify_writes as VW  # noqa: E402
import verify_writes4 as A  # noqa: E402
from phase3 import fetch_stage as F  # noqa: E402
from phase4 import model4 as M  # noqa: E402
from phase4 import verify4 as V  # noqa: E402

from tests.remediation.phase4_cases import (  # noqa: E402
    CARD,
    OLD_RAW,
    SITE_ID,
    STORED,
    Case,
    fake_card_fit,
    make_case,
    new_raw,
    plan_site,
    retitle,
    sha,
    witness,
    write_batch,
)

P4_STAMP = "phase4:p4-0001:chunk-0001"
P5_STAMP = "phase5:p5-0001:chunk-0001"


@pytest.fixture(autouse=True)
def _card_fit_without_brand_fonts(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(V, "card_fit", fake_card_fit)


def dumps(value: Any) -> str:
    """How the writer serialises raw_data (production_write: sort_keys, ensure_ascii=False)."""
    return json.dumps(value, sort_keys=True, ensure_ascii=False)


# ------------------------------------------------------------------------------------------------
# A fake production that parses what it is given
# ------------------------------------------------------------------------------------------------

_LIKE = re.compile(r"run_stamp LIKE '((?:[^']|'')*)'")
_NOT_LIKE = re.compile(r"run_stamp NOT LIKE '((?:[^']|'')*)'")
_PAIRS = re.compile(r"\(table_name, column_name\) IN \(((?:\('[^']*', '[^']*'\)(?:, )?)+)\)")
_ONE_COLUMN = re.compile(r"table_name = '([^']*)' AND column_name = '([^']*)'")
_ROW_PKS = re.compile(r"row_pk IN \(([^)]*)\)")
_UUIDS = re.compile(r"'([0-9a-f-]{36})'::uuid")
_SELECTED = re.compile(r"\(SELECT (.+?) FROM remediation_change_log")


def _like(pattern: str) -> re.Pattern[str]:
    pattern = pattern.replace("''", "'")
    return re.compile("".join(".*" if ch == "%" else re.escape(ch) for ch in pattern) + r"\Z")


@dataclass
class FakeProduction:
    """The journal and the site rows production holds; answers only the reads it can parse."""

    journal: list[dict[str, Any]] = field(default_factory=list)
    sites: dict[str, dict[str, Any]] = field(default_factory=dict)
    statements: list[str] = field(default_factory=list)

    def __call__(self, sql: str) -> str:
        self.statements.append(sql)
        body = sql.strip()
        assert body.startswith("SELECT "), f"not a read: {body[:60]}"
        assert body.count(";") == 1 and body.endswith(";"), "one statement per call"
        for word in ("UPDATE ", "INSERT ", "DELETE ", "BEGIN", "COMMIT", "apply_remediation"):
            assert word not in body, f"the acceptance sent {word!r}"
        if "FROM remediation_change_log" in body:
            return self._journal(body)
        if "FROM unified_sites u LEFT JOIN card_stats c" in body:
            return self._live(body)
        raise AssertionError(f"the fake production does not know this read: {body[:80]}")

    def _journal(self, sql: str) -> str:
        rows = list(self.journal)
        if match := _LIKE.search(sql):
            rows = [r for r in rows if _like(match.group(1)).match(r["run_stamp"])]
        if match := _NOT_LIKE.search(sql):
            rows = [r for r in rows if not _like(match.group(1)).match(r["run_stamp"])]
        if match := _PAIRS.search(sql):
            pairs = set(re.findall(r"\('([^']*)', '([^']*)'\)", match.group(1)))
            rows = [r for r in rows if (r["table_name"], r["column_name"]) in pairs]
        if match := _ONE_COLUMN.search(sql):
            rows = [r for r in rows if (r["table_name"], r["column_name"]) == match.groups()]
        if match := _ROW_PKS.search(sql):
            pks = set(re.findall(r"'([^']*)'", match.group(1)))
            rows = [r for r in rows if r["row_pk"] in pks]
        columns = [c.strip() for c in _SELECTED.search(sql).group(1).split(",")]
        rows.sort(key=lambda r: r["id"])
        return "".join(json.dumps({c: r[c] for c in columns}) + "\n" for r in rows)

    def _live(self, sql: str) -> str:
        out = []
        for site_id in _UUIDS.findall(sql):
            if site_id not in self.sites:
                continue
            row = self.sites[site_id]
            description, raw, card = row["description"], row["raw_data"], row["card_description"]
            provenance = (raw or {}).get(M.PROVENANCE_KEY) or {}
            pinned_desc = provenance.get("desc_sha256")
            pinned_card = (provenance.get("card") or {}).get("text_sha256")
            out.append(
                {
                    "id": site_id,
                    "description": description,
                    # jsonb prints its keys shorter-first: not the writer's order
                    "raw_data": None
                    if raw is None
                    else dict(sorted(raw.items(), key=lambda kv: (len(kv[0]), kv[0]))),
                    "has_card_row": row["has_card_row"],
                    "card_description": card,
                    "desc_invariant": None
                    if pinned_desc is None or description is None
                    else pinned_desc == sha(description),
                    "card_invariant": None
                    if pinned_card is None or card is None
                    else pinned_card == sha(card),
                }
            )
        return "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in out)


# ------------------------------------------------------------------------------------------------
# One written P4 step, and the P5 step after it
# ------------------------------------------------------------------------------------------------


@dataclass
class Written:
    case: Case
    run_dir: Path
    plan: list[dict[str, Any]]
    production: FakeProduction


def _plan_row(site_id: str, table: str, column: str, old: str | None, new: str | None, key: str):
    return {
        "site_id": site_id,
        "site_name": "Tarxien Temples",
        "table": table,
        "pk_column": "site_id" if table == "card_stats" else "id",
        "pk": site_id,
        "column": column,
        "old_value": old,
        "new_value": new,
        "test_id": {"description": "P4/description", "raw_data": "P4/raw_data"}.get(
            column, "P5/card"
        ),
        "evidence": [],
        "verdict": {},
        "change_key": key,
    }


def _evidence(case: Case) -> dict[str, Any]:
    """The journal's p_evidence (production_write, JOURNAL): the quote of every sentence."""
    return {
        "lane": case.assembly.provenance.lane.value,
        "sentences": [
            {
                "n": s.n,
                "quote": quote,
                "start": s.start,
                "end": s.end,
                "drop": [list(d) for d in s.drop],
            }
            for s, quote in zip(case.assembly.provenance.sentences, case.quotes, strict=True)
        ],
    }


def written_p4(
    tmp_path: Path, *, cards: bool = False, card_held: bool = False, case: Case | None = None
) -> Written:
    """The P4 rows of one site applied and journalled; with `cards`, the P5 row after them. With
    `card_held` the site is written as `write4.without_card` writes a site whose card a CARD-scope
    hold keeps back: description and raw_data with `provenance.card: null`, while the run's
    `assembly.jsonl` still carries the assembled card. `case` is the clean lane-W site unless
    given."""
    case = case or make_case()
    run_dir = tmp_path / "runs" / "pilot"
    write_batch(run_dir, case)
    written = case.assembly
    if card_held:
        written = dataclasses.replace(
            case.assembly, card=None, provenance=dataclasses.replace(written.provenance, card=None)
        )
    new = new_raw(case.site, written)
    plan = [
        _plan_row(
            SITE_ID, "unified_sites", "description", STORED, case.assembly.description, "k-desc"
        ),
        _plan_row(SITE_ID, "unified_sites", "raw_data", dumps(OLD_RAW), dumps(new), "k-raw"),
    ]
    journal = [
        {
            "id": 11,
            "table_name": "unified_sites",
            "column_name": "description",
            "row_pk": SITE_ID,
            "old_value": STORED,
            "new_value": case.assembly.description,
            "run_stamp": P4_STAMP,
            "change_key": "k-desc",
            "evidence": _evidence(case),
        },
        {
            "id": 12,
            "table_name": "unified_sites",
            "column_name": "raw_data",
            "row_pk": SITE_ID,
            "old_value": dumps(OLD_RAW),
            "new_value": dumps(new),
            "run_stamp": P4_STAMP,
            "change_key": "k-raw",
            "evidence": _evidence(case),
        },
    ]
    card = "An old card."
    if cards:
        plan = [_plan_row(SITE_ID, "card_stats", "card_description", card, CARD, "k-card")]
        journal.append(
            {
                "id": 13,
                "table_name": "card_stats",
                "column_name": "card_description",
                "row_pk": SITE_ID,
                "old_value": card,
                "new_value": CARD,
                "run_stamp": P5_STAMP,
                "change_key": "k-card",
                "evidence": {"lane": "W"},
            }
        )
        card = CARD
    production = FakeProduction(
        journal=journal,
        sites={
            SITE_ID: {
                "description": case.assembly.description,
                "raw_data": new,
                "card_description": card,
                "has_card_row": True,
            }
        },
    )
    return Written(case, run_dir, plan, production)


def _args(written: Written, tmp_path: Path, lane: str = "p4", **over: Any) -> Any:
    plan = tmp_path / f"PLAN_{lane}.jsonl"
    lanes.write_jsonl(plan, written.plan)
    values = {
        "lane": lane,
        "plan": str(plan),
        "run": [str(written.run_dir)],
        "stamp_like": {"p4": "phase4:%", "p4l": "phase4l:%", "p5": "phase5:%"}[lane],
        "complete": False,
    }
    values.update(over)
    return type("Args", (), values)()


def accept(written: Written, tmp_path: Path, lane: str = "p4", **over: Any) -> list[str]:
    return A.accept_lane(_args(written, tmp_path, lane, **over), run=written.production)


# ------------------------------------------------------------------------------------------------
# The whole acceptance
# ------------------------------------------------------------------------------------------------


def test_a_written_p4_step_is_accepted(tmp_path: Path) -> None:
    written = written_p4(tmp_path)
    assert accept(written, tmp_path) == []
    assert all(s.lstrip().startswith("SELECT ") for s in written.production.statements)


def test_a_written_p5_step_is_accepted_with_the_card_read_back(tmp_path: Path) -> None:
    written = written_p4(tmp_path, cards=True)
    assert accept(written, tmp_path, "p5") == []


def test_the_live_read_uses_the_key_columns_own_type() -> None:
    """0022: `id::text IN (...)` scans the whole table; the key is compared as a uuid."""
    sql = A.live_sql([SITE_ID])
    assert f"u.id IN ('{SITE_ID}'::uuid)" in sql and "id::text IN" not in sql
    assert "encode(sha256(convert_to(u.description, 'UTF8')), 'hex')" in sql


def test_the_lane_read_leaves_out_reversals_and_the_chain_read_keeps_them() -> None:
    assert "run_stamp NOT LIKE '%-rollback'" in A.lane_journal_sql("phase4:%")
    chain = A.chain_sql([SITE_ID], A.LANE_COLUMNS["p4"])
    assert "run_stamp" not in chain.split("WHERE", 1)[1]  # every stamp is a link
    assert "('unified_sites', 'description'), ('unified_sites', 'raw_data')" in chain


def test_main_prints_its_own_exit_line_and_reads_the_lane_from_lanes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    written = written_p4(tmp_path)
    args = _args(written, tmp_path)
    monkeypatch.setattr(lanes, "psql", lambda sql, *, host: written.production(sql))
    seen: list[str] = []

    def lane(name: str) -> Any:
        seen.append(name)
        return type("Lane", (), {"stamp_like": "phase4:%"})()

    monkeypatch.setattr(lanes, "lane", lane)
    code = A.main(["--lane", "p4", "--plan", args.plan, "--run", *args.run])
    out = capsys.readouterr().out.strip().splitlines()
    assert (code, out[-1], seen) == (0, "ACCEPT_EXIT=0", ["p4"])
    written.production.sites[SITE_ID]["description"] = "Changed by hand."
    assert A.main(["--lane", "p4", "--plan", args.plan, "--run", *args.run]) == 1
    assert capsys.readouterr().out.strip().splitlines()[-1] == "ACCEPT_EXIT=1"


def test_main_needs_exactly_one_mode_and_a_run_for_the_text_lanes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with pytest.raises(SystemExit):
        A.main([])
    with pytest.raises(SystemExit):
        A.main(["--lane", "p4", "--boot-logs", "--since", "2026-09-24T10:00:00Z"])
    written = written_p4(tmp_path)
    with pytest.raises(SystemExit, match="--run is required"):
        accept(written, tmp_path, run=None)


# ------------------------------------------------------------------------------------------------
# 1. The journal chain
# ------------------------------------------------------------------------------------------------


def _accept4(written: Written, *, complete: bool = False, lane: str = "p4") -> A.Acceptance4:
    columns = A.LANE_COLUMNS[lane]
    production = A.read_production(
        sorted({row["pk"] for row in written.plan}),
        stamp_like={"p4": "phase4:%", "p5": "phase5:%"}[lane],
        columns=columns,
        run=written.production,
    )
    return A.accept4(
        planned=written.plan,
        lane_links=production.lane_links,
        chains=production.chains,
        live=production.live,
        present=production.present,
        columns=columns,
        complete=complete,
        change_keys=production.change_keys,
    )


def test_raw_data_is_compared_as_json_not_as_postgres_text(tmp_path: Path) -> None:
    """The fake prints jsonb keys shorter-first, as Postgres does; the writer sorted them."""
    result = _accept4(written_p4(tmp_path))
    assert result.deviations == []
    assert len(result.carried) == 2


def test_a_planned_row_the_lane_has_not_written_yet_must_hold_its_old_value(tmp_path: Path) -> None:
    written = written_p4(tmp_path)
    written.production.journal = [r for r in written.production.journal if r["id"] != 11]
    written.production.sites[SITE_ID]["description"] = STORED
    result = _accept4(written)
    assert result.untouched == 1 and not any("MOVED" in d for d in result.deviations)
    assert any("NOT WRITTEN" in d for d in _accept4(written, complete=True).deviations)
    written.production.sites[SITE_ID]["description"] = "Edited in db.html."
    assert any(d.startswith("MOVED") for d in _accept4(written).deviations)


def test_a_lane_row_with_another_value_than_the_plan_is_a_deviation(tmp_path: Path) -> None:
    written = written_p4(tmp_path)
    written.plan[0]["new_value"] = "Another description."
    assert any(d.startswith("OTHER VALUE") for d in _accept4(written).deviations)


def test_a_row_written_twice_or_changed_later_is_a_deviation(tmp_path: Path) -> None:
    written = written_p4(tmp_path)
    first = written.production.journal[0]
    again = dict(first, id=21, old_value=first["new_value"], new_value="Once more.")
    written.production.journal.append(again)
    written.production.sites[SITE_ID]["description"] = "Once more."
    deviations = _accept4(written).deviations
    assert any(d.startswith("WRITTEN TWICE") for d in deviations)
    written = written_p4(tmp_path / "later")
    later = dict(written.production.journal[0], id=22, run_stamp="phase3:batch-0009:chunk-0001")
    later.update(old_value=later["new_value"], new_value="Rewritten by another lane.")
    written.production.journal.append(later)
    written.production.sites[SITE_ID]["description"] = "Rewritten by another lane."
    result = _accept4(written)
    assert any(d.startswith("CHANGED LATER") for d in result.deviations)
    assert ("unified_sites", "description", SITE_ID) not in result.carried


P4_ROUND_2 = "phase4:p4-0001:chunk-0002"


def _revert(
    written: Written, *, key_suffix: str = "-rollback", reversal_stamp: str | None = None
) -> None:
    """revert4's reversal of the round-1 rows: each row's transition back, journalled under the
    write's key and its stamp plus `-rollback` (or the key suffix / stamp given); the fields hold
    their old values again."""
    rows = [row for row in written.production.journal if row["run_stamp"] == P4_STAMP]
    first = max(row["id"] for row in written.production.journal) + 1
    for offset, row in enumerate(rows):
        written.production.journal.append(
            dict(
                row,
                id=first + offset,
                old_value=row["new_value"],
                new_value=row["old_value"],
                run_stamp=P4_STAMP + "-rollback" if reversal_stamp is None else reversal_stamp,
                change_key=row["change_key"] + key_suffix,
                evidence={},
            )
        )
    written.production.sites[SITE_ID].update(description=STORED, raw_data=OLD_RAW)


def _write_round_2(written: Written) -> None:
    """write_gate4 `--apply --round 2`: the same batch, the same keys, a new chunk stamp."""
    rows = [row for row in written.production.journal if row["run_stamp"] == P4_STAMP]
    first = max(row["id"] for row in written.production.journal) + 1
    for offset, row in enumerate(rows):
        written.production.journal.append(dict(row, id=first + offset, run_stamp=P4_ROUND_2))
    written.production.sites[SITE_ID].update(
        description=written.case.assembly.description,
        raw_data=new_raw(written.case.site, written.case.assembly),
    )


def test_a_reverted_step_written_again_as_round_2_is_accepted(tmp_path: Path) -> None:
    """Follow-up of wip/p4-write-sup: a lane row with its own kept reversal is reverted, not
    'changed later', and the round-2 write of the same key is not 'written twice'."""
    written = written_p4(tmp_path)
    _revert(written)
    _write_round_2(written)
    result = _accept4(written)
    assert result.deviations == [] and len(result.carried) == 2
    assert accept(written, tmp_path) == []


def test_a_reverted_step_counts_as_not_yet_written(tmp_path: Path) -> None:
    written = written_p4(tmp_path)
    _revert(written)
    result = _accept4(written)
    assert (result.deviations, result.carried, result.untouched) == ([], set(), 2)
    assert (
        sum(d.startswith("NOT WRITTEN") for d in _accept4(written, complete=True).deviations) == 2
    )
    assert accept(written, tmp_path) == []
    written.production.sites[SITE_ID]["description"] = "Edited after the revert."
    assert any(d.startswith("NOT NEW") for d in _accept4(written).deviations)


#: A second site of the same chunk (the mass run's mid-run audit, 2026-09-25: one WRONG_SITE site
#: of a written 9-site chunk is taken back alone with `revert4 --site`).
SITE_B = "318414bc-2222-4222-8222-222222222222"
B_STORED = "An LLM wrote this in March about another site."
B_WRITTEN = "The second site's written description [1]."


def _second_site(written: Written) -> None:
    """Site B written by the same chunk as the case's site: its two planned rows, their journal rows
    under the same stamp, and production holding their new values."""
    new_raw_b = {"description_citations": [], "k": "written"}
    written.plan += [
        _plan_row(SITE_B, "unified_sites", "description", B_STORED, B_WRITTEN, "k-desc-b"),
        _plan_row(SITE_B, "unified_sites", "raw_data", dumps(OLD_RAW), dumps(new_raw_b), "k-raw-b"),
    ]
    for offset, (column, old, new, key) in enumerate(
        (
            ("description", B_STORED, B_WRITTEN, "k-desc-b"),
            ("raw_data", dumps(OLD_RAW), dumps(new_raw_b), "k-raw-b"),
        )
    ):
        written.production.journal.append(
            {
                "id": 31 + offset,
                "table_name": "unified_sites",
                "column_name": column,
                "row_pk": SITE_B,
                "old_value": old,
                "new_value": new,
                "run_stamp": P4_STAMP,
                "change_key": key,
                "evidence": {},
            }
        )
    written.production.sites[SITE_B] = {
        "description": B_WRITTEN,
        "raw_data": new_raw_b,
        "card_description": None,
        "has_card_row": False,
    }


def _revert_site(written: Written, site_id: str) -> None:
    """revert4 `--site`: the site's rows of the chunk written back, journalled under the write's key
    and its stamp plus `-rollback`; the chunk's other site untouched."""
    rows = [
        row
        for row in written.production.journal
        if row["run_stamp"] == P4_STAMP and row["row_pk"] == site_id
    ]
    first = max(row["id"] for row in written.production.journal) + 1
    for offset, row in enumerate(rows):
        written.production.journal.append(
            dict(
                row,
                id=first + offset,
                old_value=row["new_value"],
                new_value=row["old_value"],
                run_stamp=P4_STAMP + "-rollback",
                change_key=row["change_key"] + "-rollback",
                evidence={},
            )
        )
    written.production.sites[site_id].update(description=B_STORED, raw_data=OLD_RAW)


def test_a_site_reverted_alone_is_not_yet_written_and_its_chunk_is_still_accepted(
    tmp_path: Path,
) -> None:
    """After `revert4 --site` the site's rows are reversals of their own and its planned rows -
    still in the lane plan, which keeps what was written - are judged like a reverted batch's: not
    yet written, at their old value. The chunk's other site is carried and verified again: 0
    deviations. A later edit of the reverted site is still seen."""
    written = written_p4(tmp_path)
    _second_site(written)
    assert _accept4(written).deviations == []
    _revert_site(written, SITE_B)
    result = _accept4(written)
    assert result.deviations == [] and result.untouched == 2
    assert {key[2] for key in result.carried} == {SITE_ID}
    assert accept(written, tmp_path) == []
    written.production.sites[SITE_B]["description"] = "Edited after the revert."
    assert any(d.startswith("NOT NEW") for d in _accept4(written).deviations)


def test_only_a_rows_own_reversal_closes_it(tmp_path: Path) -> None:
    """The key **and** the stamp plus `-rollback` (revert4 `_reversed`): a reversal journalled
    under another key, or under round 2's stamp, does not close a round-1 row."""
    written = written_p4(tmp_path)
    _revert(written, key_suffix="-other")
    assert any(d.startswith("CHANGED LATER") for d in _accept4(written).deviations)
    written = written_p4(tmp_path / "stamp")
    _revert(written, reversal_stamp=P4_ROUND_2 + "-rollback")
    assert any(d.startswith("CHANGED LATER") for d in _accept4(written).deviations)
    # round 2 on top of a live round 1, no reversal between: two open writes of one row
    written = written_p4(tmp_path / "twice")
    _write_round_2(written)
    assert any(d.startswith("WRITTEN TWICE") for d in _accept4(written).deviations)
    # a journal row without a change key (the column is nullable) is read like any write ...
    written = written_p4(tmp_path / "keyless")
    for row in written.production.journal:
        row["change_key"] = None
    assert _accept4(written).deviations == []
    # ... and has no reversal of its own, even one under its stamp plus -rollback: in SQL
    # `NULL || '-rollback'` is NULL and equals nothing, so revert4 does not see it reverted either
    written = written_p4(tmp_path / "keyless-reverted")
    _revert(written)
    for row in written.production.journal:
        row["change_key"] = None
    assert any(d.startswith("CHANGED LATER") for d in _accept4(written).deviations)


def test_a_planned_row_outside_the_lanes_columns_is_a_deviation(tmp_path: Path) -> None:
    written = written_p4(tmp_path)
    written.plan.append(
        _plan_row(SITE_ID, "card_stats", "card_description", "An old card.", CARD, "k-card")
    )
    assert any(d.startswith("PLANNED OUTSIDE THE LANE") for d in _accept4(written).deviations)


def test_a_site_written_with_its_card_held_is_accepted(tmp_path: Path) -> None:
    """C4: write4 writes a card-held site with `provenance.card: null`; the run's assembly still
    has its card. The re-verification takes the run's card only where production pins one."""
    written = written_p4(tmp_path, card_held=True)
    raw = written.production.sites[SITE_ID]["raw_data"]
    assert raw[M.PROVENANCE_KEY]["card"] is None
    assert A.index_run(written.run_dir)[SITE_ID].assembly.card == CARD
    assert accept(written, tmp_path) == []


def test_a_live_value_that_is_not_the_chains_last_is_a_deviation(tmp_path: Path) -> None:
    written = written_p4(tmp_path)
    written.production.sites[SITE_ID]["description"] = "Overwritten without a journal row."
    assert any(d.startswith("NOT NEW") for d in _accept4(written).deviations)


def test_a_lane_row_outside_the_plan_or_the_lanes_columns_is_a_deviation(tmp_path: Path) -> None:
    written = written_p4(tmp_path)
    written.plan = written.plan[:1]
    assert any(d.startswith("OUTSIDE THE PLAN") for d in _accept4(written).deviations)
    written = written_p4(tmp_path / "card")
    card = dict(
        written.production.journal[0],
        id=30,
        table_name="card_stats",
        column_name="card_description",
        old_value="An old card.",
        new_value=CARD,
    )
    written.production.journal.append(card)
    written.production.sites[SITE_ID]["card_description"] = CARD
    assert any(d.startswith("OUTSIDE THE LANE") for d in _accept4(written).deviations)


def test_a_planned_site_missing_from_the_database_is_a_deviation(tmp_path: Path) -> None:
    written = written_p4(tmp_path)
    written.production.journal = []
    written.production.sites = {}
    assert any(d.startswith("MISSING") for d in _accept4(written).deviations)


def test_the_chain_is_judged_by_the_phase3_reader(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """`verify_writes.check_chain` is imported, not copied: its verdict is the acceptance's."""
    calls: list[Any] = []

    def spy(key: Any, chain: Any, live: Any, *, missing: bool) -> tuple[list[str], Any]:
        calls.append(key)
        return ["BROKEN CHAIN (spy)"], None

    monkeypatch.setattr(VW, "check_chain", spy)
    result = _accept4(written_p4(tmp_path))
    assert calls and "BROKEN CHAIN (spy)" in result.deviations and not result.carried


# ------------------------------------------------------------------------------------------------
# 2-4. V1-V15 on the read-back, the invariants, T08
# ------------------------------------------------------------------------------------------------


def test_a_written_site_that_no_longer_verifies_is_a_deviation(tmp_path: Path) -> None:
    """The run's pinned text changed after the write: V1 on the read-back says so."""
    written = written_p4(tmp_path)
    store = F.EvidenceStore(written.run_dir / "p4-0001" / M.EVIDENCE_DIR)
    path = store.path_for(SITE_ID, "src.W.txt")
    path.write_bytes(path.read_bytes().replace(b"Tarxien.", b"Tarxien!"))
    deviations = accept(written, tmp_path)
    assert any(d.startswith(f"REVERIFY {SITE_ID} V1") for d in deviations)


def test_the_read_back_is_verified_with_the_sites_pinned_wikidata_item(tmp_path: Path) -> None:
    """V6 accepts the pinned item's English label for a strong 'own' verdict (pilot 1, T8): the
    acceptance re-verifies with the run's `src.D`, as the batch was verified before the write."""
    case = make_case(site=plan_site(name="Ħal Tarxien megaliths", aliases=()))
    case = dataclasses.replace(retitle(case, "Ħal Tarxien (Paola)"), witness=witness())
    written = written_p4(tmp_path, case=case)
    assert accept(written, tmp_path) == []


def test_the_journal_quotes_are_the_ones_verified(tmp_path: Path) -> None:
    written = written_p4(tmp_path)
    evidence = written.production.journal[0]["evidence"]
    evidence["sentences"][1]["quote"] = evidence["sentences"][1]["quote"].replace("1915", "1916")
    deviations = accept(written, tmp_path)
    assert any(d.startswith(f"REVERIFY {SITE_ID} V2") for d in deviations)


def test_journal_evidence_without_quotes_or_with_other_offsets_is_a_deviation(
    tmp_path: Path,
) -> None:
    written = written_p4(tmp_path)
    written.production.journal[0]["evidence"] = {"lane": "W"}
    assert any("one quote per published sentence" in d for d in accept(written, tmp_path))
    written = written_p4(tmp_path / "offsets")
    written.production.journal[0]["evidence"]["sentences"][0]["start"] += 1
    assert any("other offsets" in d for d in accept(written, tmp_path))


def test_the_in_database_invariants_are_postgres_own(tmp_path: Path) -> None:
    written = written_p4(tmp_path)
    production = A.read_production(
        [SITE_ID], stamp_like="phase4:%", columns=A.LANE_COLUMNS["p4"], run=written.production
    )
    carried = {("unified_sites", "description", SITE_ID)}
    assert A.invariant_deviations(lane="p4", carried=carried, production=production) == []
    production.rows[SITE_ID]["desc_invariant"] = False
    assert A.invariant_deviations(lane="p4", carried=carried, production=production)
    production.rows[SITE_ID]["desc_invariant"] = None  # NULL: no provenance at all
    assert A.invariant_deviations(lane="p4", carried=carried, production=production)


def test_a_card_that_is_not_the_pinned_one_fails_the_p5_invariant(tmp_path: Path) -> None:
    written = written_p4(tmp_path, cards=True)
    written.production.sites[SITE_ID]["card_description"] = CARD + " "
    written.production.journal[-1]["new_value"] = CARD + " "
    written.plan[0]["new_value"] = CARD + " "
    deviations = accept(written, tmp_path, "p5")
    assert any(d.startswith(f"INVARIANT {SITE_ID}: card.text_sha256") for d in deviations)
    assert any(d.startswith(f"REVERIFY {SITE_ID} V13") for d in deviations)


def test_the_legacy_lane_needs_its_provenance_and_the_invariant(tmp_path: Path) -> None:
    written = written_p4(tmp_path)
    legacy = M.LegacyProvenance(desc_sha256=sha(STORED))
    raw = dict(OLD_RAW, **{M.PROVENANCE_KEY: legacy.to_dict()})
    written.plan = [
        _plan_row(SITE_ID, "unified_sites", "raw_data", dumps(OLD_RAW), dumps(raw), "k-legacy")
    ]
    written.production.journal = [
        dict(
            written.production.journal[1],
            id=40,
            new_value=dumps(raw),
            run_stamp="phase4l:p4l-0001:chunk-0001",
        )
    ]
    written.production.sites[SITE_ID].update(description=STORED, raw_data=raw)
    assert accept(written, tmp_path, "p4l") == []
    written.production.sites[SITE_ID]["description"] = "The text changed under the claim."
    assert any("desc_sha256 is not" in d for d in accept(written, tmp_path, "p4l"))


def test_a_legacy_provenance_that_does_not_read_is_a_deviation(tmp_path: Path) -> None:
    production = A.Production(
        lane_links=[],
        chains={},
        live={},
        present=set(),
        change_keys={},
        rows={
            SITE_ID: {
                "desc_invariant": True,
                "raw_data": {M.PROVENANCE_KEY: {"lane": "L", "basis": "a guess"}},
            }
        },
    )
    carried = {("unified_sites", "raw_data", SITE_ID)}
    deviations = A.invariant_deviations(lane="p4l", carried=carried, production=production)
    assert any("the legacy provenance does not read" in d for d in deviations)


def test_t08_runs_over_the_written_sites() -> None:
    production = A.Production(
        lane_links=[],
        chains={},
        live={},
        present=set(),
        change_keys={},
        rows={
            SITE_ID: {
                "description": "A temple [1]. A wall [2].",
                "raw_data": {"description_citations": [{"n": 1, "url": "u"}]},
            }
        },
    )
    deviations = A.t08_deviations([SITE_ID], production)
    assert deviations and deviations[0].startswith(f"T08 {SITE_ID} T08/marker-without-entry")


# ------------------------------------------------------------------------------------------------
# 5-6. The card file and the boot logs
# ------------------------------------------------------------------------------------------------


def test_the_card_file_check_reads_the_tools_own_exit_line(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    card_json = tmp_path / "card_json.py"
    monkeypatch.setattr(A, "CARD_JSON", card_json)
    assert A.card_file_deviations(lambda argv: (0, "")) == [
        f"CARD FILE: {card_json} is not on this tree (WB-D3)"
    ]
    card_json.write_text("", encoding="utf-8")
    seen: list[list[str]] = []

    def command(output: str, status: int = 0) -> Any:
        def run(argv: Any) -> tuple[int, str]:
            seen.append(list(argv))
            return status, output

        return run

    assert A.card_file_deviations(command("4,996 entries equal\nSTAGE_EXIT=0\n")) == []
    assert seen[-1][1:] == [str(card_json), "--check"]
    assert A.card_file_deviations(command("1 entry differs\nSTAGE_EXIT=1\n"))
    assert A.card_file_deviations(command("no exit line at all\n"))
    # a wrapper's status is not read: exit status 0 with a failing exit line still fails
    assert A.card_file_deviations(command("WRITE_EXIT=0\nSTAGE_EXIT=3\n", status=0))


def test_the_boot_logs_of_both_containers_carry_no_overwrite() -> None:
    since = "2026-09-24T10:00:00.123456789Z"
    seen: list[list[str]] = []

    def logs(argv: Any) -> tuple[int, str]:
        seen.append(list(argv))
        if argv[-1] == "ancient_nerds_api2":
            return 0, (
                "[STARTUP] Card descriptions already up to date (4996 checked)\n"
                "WARNING [STARTUP] Card description overwritten: 4a5a 'a' -> 'b'\n"
            )
        return 0, "[STARTUP] Card descriptions already up to date (4996 checked)\n"

    deviations = A.boot_log_deviations(since, host="ancientnerds", command=logs)
    assert deviations == [
        "BOOT LOG ancient_nerds_api2: 1 '[STARTUP] Card description overwritten' line(s)"
    ]
    assert seen == [
        ["ssh", "ancientnerds", "docker", "logs", "--since", since, "ancient_nerds_api"],
        ["ssh", "ancientnerds", "docker", "logs", "--since", since, "ancient_nerds_api2"],
    ]
    assert A.boot_log_deviations(since, host="h", command=lambda argv: (255, "")) == [
        "BOOT LOG ancient_nerds_api: docker logs exited 255",
        "BOOT LOG ancient_nerds_api2: docker logs exited 255",
    ]


def test_the_boot_log_instant_is_checked_before_it_reaches_a_remote_shell() -> None:
    with pytest.raises(SystemExit, match="RFC 3339"):
        A.boot_log_deviations("now; rm -rf /", host="h", command=lambda argv: (0, ""))


def test_a_plan_row_without_its_keys_is_refused(tmp_path: Path) -> None:
    plan = tmp_path / "PLAN.jsonl"
    lanes.write_jsonl(plan, [{"site_id": SITE_ID, "table": "unified_sites"}])
    with pytest.raises(SystemExit, match="a planned row without"):
        A.read_plan(plan)


def test_a_run_batch_that_cannot_be_read_stops_the_acceptance(tmp_path: Path) -> None:
    written = written_p4(tmp_path)
    (written.run_dir / "p4-0001" / M.ASSEMBLY_FILE).unlink()
    with pytest.raises(SystemExit, match="cannot be read"):
        A.index_run(written.run_dir)


def test_a_case_without_provenance_in_production_is_a_deviation(tmp_path: Path) -> None:
    written = written_p4(tmp_path)
    raw = dict(written.production.sites[SITE_ID]["raw_data"])
    raw[M.PROVENANCE_KEY] = dict(raw[M.PROVENANCE_KEY], v=2)
    written.production.sites[SITE_ID]["raw_data"] = raw
    written.production.journal[1]["new_value"] = dumps(raw)
    written.plan[1]["new_value"] = dumps(raw)
    deviations = accept(written, tmp_path)
    assert any("the written provenance does not read" in d for d in deviations)


def test_the_run_index_carries_the_plan_record_and_the_assembly(tmp_path: Path) -> None:
    written = written_p4(tmp_path)
    index = A.index_run(written.run_dir)
    entry = index[SITE_ID]
    assert entry.site == written.case.site and entry.assembly == written.case.assembly
    assert dataclasses.replace(entry, assembly=None).assembly is None


def test_a_lane_written_from_two_runs_is_read_from_both(tmp_path: Path) -> None:
    written = written_p4(tmp_path / "pilot")
    empty = tmp_path / "mass"
    empty.mkdir()
    assert accept(written, tmp_path, run=[str(empty), str(written.run_dir)]) == []
    assert A.index_runs([empty, written.run_dir]) == A.index_run(written.run_dir)


def test_a_site_two_runs_carry_is_refused(tmp_path: Path) -> None:
    first = written_p4(tmp_path / "a")
    second = written_p4(tmp_path / "b")
    with pytest.raises(SystemExit, match="is in two runs"):
        A.index_runs([first.run_dir, second.run_dir])


def test_a_batch_without_a_written_site_is_not_read(tmp_path: Path) -> None:
    written = written_p4(tmp_path)
    later = written.run_dir / "p4-0099"
    later.mkdir()
    (later / M.INPUT_FILE).write_text(
        json.dumps({"batch_id": "p4-0099", "ordinal": 99, "sites": [{"site_id": "later-site"}]}),
        encoding="utf-8",
    )
    assert accept(written, tmp_path) == []
    assert A.index_run(written.run_dir, {SITE_ID}) == A.index_run(written.run_dir, [SITE_ID])
    with pytest.raises(SystemExit, match="cannot be read"):
        A.index_run(written.run_dir, {"later-site"})
