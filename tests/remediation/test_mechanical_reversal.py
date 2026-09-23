"""The journal-reversal lane: undo exactly the named rows, each on the evidence it names.

`classify_reversal` is pure; `load_state` is driven by a stand-in for production that answers
only the three statements it sends - and checks that each names the rows it must.
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
from mechanical import plan as P  # noqa: E402
from mechanical import reversal as R  # noqa: E402

AHIN = "786cada5-1feb-4c5c-9e79-b8ffdf8aacc6"
STANY = "60722e7e-587a-46fb-b09c-e6e82f1b74f7"
DESCRIPTION = "A Kushan-era Buddhist stupa and monastery near Jalalabad, Afghanistan, excavated."


def reason(**over: Any) -> R.Reason:
    base: dict[str, Any] = {
        "journal_id": 28384,
        "site_id": AHIN,
        "name": "Ahin Posh Tape",
        "column": "country",
        "reason": "phase 3 followed a conflated Wikidata item",
        "quotes": (
            R.Quote("description", "near Jalalabad, Afghanistan"),
            R.Quote("wikidata:Q4695118", "human settlement in Pakistan"),
        ),
        "residual": "the point stays in Pakistan",
    }
    base.update(over)
    return R.Reason(**base)


def entry(**over: Any) -> dict[str, Any]:
    base = {
        "id": 28384,
        "row_pk": AHIN,
        "table_name": "unified_sites",
        "column_name": "country",
        "old_value": "Afghanistan",
        "new_value": "Pakistan",
        "run_stamp": "phase3:batch-0121:chunk-0006",
        "test_id": "P3/country",
    }
    base.update(over)
    return base


def cell(**over: Any) -> R.Cell:
    base: dict[str, Any] = {
        "entry": entry(),
        "site": {
            "id": AHIN,
            "name": "Ahin Posh Tape",
            "source_id": "ancient_nerds",
            "description": DESCRIPTION,
            "country": "Pakistan",
            "period_start": "1",
        },
        "chain": (
            P.JournalLink(
                28384, "phase3:batch-0121:chunk-0006", "P3/country", "Afghanistan", "Pakistan"
            ),
        ),
        "live": "Pakistan",
    }
    base.update(over)
    return R.Cell(**base)


PAGES = {"wikidata:Q4695118": '{"descriptions": {"en": {"value": "human settlement in Pakistan"}}}'}


def decide(r: R.Reason | None = None, c: R.Cell | None = None, **kw: Any) -> P.Verdict:
    return R.classify_reversal(
        r or reason(),
        c or cell(),
        lane=L.REVERSAL_1,
        pages=kw.get("pages", PAGES),
        gold=kw.get("gold", {}),
    )


class TestTheDecision:
    def test_the_named_row_is_undone_from_the_value_it_wrote(self) -> None:
        v = decide()
        assert v.ok and (v.column, v.old_value, v.new_value, v.journal_id) == (
            "country",
            "Pakistan",
            "Afghanistan",
            28384,
        )
        assert v.evidence[0]["source"] == "remediation_change_log:28384"
        assert v.evidence[-1] == {
            "source": "residual",
            "url": "REASONS.json",
            "quote": "the point stays in Pakistan",
        }

    @pytest.mark.parametrize(
        ("change", "why"),
        [
            ({"entry": None}, "journal-row-missing"),
            ({"entry": entry(column_name="site_type")}, "journal-row-is-another-cell"),
            ({"entry": entry(row_pk=STANY)}, "journal-row-is-another-cell"),
            ({"site": None}, "row-not-in-curated-source"),
            ({"live": "India"}, "journal-disagrees"),
        ],
    )
    def test_each_check_refuses_with_its_reason(self, change: dict[str, Any], why: str) -> None:
        v = decide(c=cell(**change))
        assert not v.ok and v.reason == why and v.journal_id is None

    def test_a_row_another_write_superseded_is_not_undone(self) -> None:
        later = P.JournalLink(29000, "2026-09-22_mechanical-uk-parts", "B9", "Pakistan", "Pakistan")
        v = decide(c=cell(chain=(*cell().chain, later)))
        assert (v.ok, v.reason) == (False, "not-the-last-write")

    def test_a_broken_chain_is_refused(self) -> None:
        stray = P.JournalLink(28000, "x", "t", "Iran", "India")
        assert decide(c=cell(chain=(stray, *cell().chain))).reason == "journal-chain-broken"

    def test_a_row_that_replaced_null_is_not_restored(self) -> None:
        v = decide(
            c=cell(
                entry=entry(old_value=None),
                chain=(P.JournalLink(28384, "p", "t", None, "Pakistan"),),
            )
        )
        assert v.reason == "restores-null"

    def test_a_column_the_lane_does_not_own_is_refused(self) -> None:
        v = decide(
            r=reason(column="site_type"),
            c=cell(entry=entry(column_name="site_type"), chain=()),
        )
        assert v.reason == "column-not-owned"

    @pytest.mark.parametrize(
        ("quotes", "pages"),
        [
            ((R.Quote("description", "near Kabul"),), PAGES),
            ((R.Quote("wikidata:Q4695118", "human settlement in Pakistan"),), {}),
            ((R.Quote("enwiki:Ahin Posh", "Jalalabad"),), {"enwiki:Ahin Posh": "Peshawar"}),
            ((R.Quote("twitter", "x"),), PAGES),
        ],
    )
    def test_evidence_that_is_not_where_it_says_refuses(self, quotes: tuple, pages: dict) -> None:
        v = decide(r=reason(quotes=quotes), pages=pages)
        assert v.reason == "evidence-not-found"

    def test_a_quote_of_a_source_this_lane_cannot_check_refuses(self) -> None:
        v = decide(r=reason(quotes=(R.Quote("twitter:x", "near Jalalabad, Afghanistan"),)))
        assert (v.reason, v.note) == (
            "evidence-not-found",
            "'twitter:x' is not a source this lane can check",
        )

    def test_a_restored_value_the_column_cannot_read_is_refused(self) -> None:
        """The journal records text; a value `period_start` would not print the same way is not
        the value that row replaced, whatever the evidence says."""
        v = decide(
            r=reason(
                journal_id=28018,
                column="period_start",
                quotes=(R.Quote("description", "near Jalalabad, Afghanistan"),),
            ),
            c=cell(
                entry=entry(
                    id=28018, column_name="period_start", old_value="-03000", new_value="1"
                ),
                chain=(P.JournalLink(28018, "phase3:b", "P3/period_start", "-03000", "1"),),
                live="1",
            ),
        )
        assert (v.ok, v.reason) == (False, "restored-value-unreadable")
        assert "is not how the database prints -3000" in v.note


def gold(verdict: str = "CORRECT", value: int = -3000) -> dict[str, Any]:
    return {
        STANY: {
            "site_id": STANY,
            "db_fields": {"period_start": value},
            "verdicts": [
                {
                    "field": "period_start",
                    "verdict": verdict,
                    "note": "Bucket sort key. Bucket correct.",
                }
            ],
        }
    }


class TestTheGoldStandard:
    def stany(self) -> tuple[R.Reason, R.Cell]:
        r = reason(
            journal_id=28018,
            site_id=STANY,
            name="Stanydale Temple",
            column="period_start",
            quotes=(R.Quote(f"gold_standard:{STANY}", "Bucket correct."),),
        )
        c = cell(
            entry=entry(
                id=28018,
                row_pk=STANY,
                column_name="period_start",
                old_value="-3000",
                new_value="-2500",
            ),
            site={
                "id": STANY,
                "name": "Stanydale Temple",
                "source_id": "ancient_nerds",
                "description": "",
                "country": "Scotland",
                "period_start": "-2500",
            },
            chain=(P.JournalLink(28018, "phase3:batch-0052", "P3/period_start", "-3000", "-2500"),),
            live="-2500",
        )
        return r, c

    def test_a_value_the_gold_standard_judged_correct_is_restored_with_its_bucket(self) -> None:
        v = decide(*self.stany(), gold=gold())
        assert v.ok and (v.old_value, v.new_value) == ("-2500", "-3000")
        bucket = next(e for e in v.evidence if e["source"].endswith("categorize_period"))
        assert bucket["quote"].endswith("- the same bucket")

    @pytest.mark.parametrize(("verdict", "value"), [("WRONG", -3000), ("CORRECT", -2000)])
    def test_the_gold_standard_must_judge_the_restored_value_itself(
        self, verdict: str, value: int
    ) -> None:
        v = decide(*self.stany(), gold=gold(verdict, value))
        assert v.reason == "evidence-not-found"

    def test_a_gold_record_of_another_site_does_not_count(self) -> None:
        r, c = self.stany()
        r = replace(r, quotes=(R.Quote(f"gold_standard:{AHIN}", "Bucket correct."),))
        assert decide(r, c, gold={AHIN: gold()[STANY]}).reason == "evidence-not-found"


class Production:
    """Answers the three statements `load_state` sends, and refuses any other."""

    def __init__(self) -> None:
        self.sent: list[str] = []

    def __call__(self, sql: str) -> list[dict[str, Any]]:
        self.sent.append(sql)
        if sql.startswith("SELECT id, row_pk, table_name"):
            assert "WHERE id IN (28384)" in sql
            return [entry()]
        if sql.startswith(
            "SELECT id::text AS id, name, source_id, description, country::text AS country, period_start::text AS period_start FROM unified_sites"
        ):
            assert re.search(rf"WHERE id IN \('{AHIN}'\)$", sql), "the key's own type, not id::text"
            return [
                {
                    "id": AHIN,
                    "name": "Ahin Posh Tape",
                    "source_id": "ancient_nerds",
                    "description": DESCRIPTION,
                    "country": "Pakistan",
                    "period_start": "1",
                }
            ]
        if sql.startswith("SELECT id, row_pk, column_name, run_stamp"):
            assert "column_name IN ('country')" in sql and f"row_pk IN ('{AHIN}')" in sql
            assert sql.endswith("ORDER BY id")
            return [{**entry(), "row_pk": AHIN}]
        raise AssertionError(f"unexpected statement: {sql[:80]!r}")


def test_load_state_reads_the_row_the_site_and_the_chain() -> None:
    production = Production()
    state = R.load_state(production, [reason()])
    c = state[28384]
    assert c.live == "Pakistan" and [link.id for link in c.chain] == [28384]
    assert len(production.sent) == 3


class TestTheList:
    def write(self, tmp_path: Path, ids: list[int]) -> Path:
        entries = [
            {
                "journal_id": i,
                "site_id": AHIN,
                "name": "x",
                "column": "country",
                "reason": "r",
                "quotes": [{"source": "description", "text": "t"}],
            }
            for i in ids
        ]
        path = tmp_path / "REASONS.json"
        path.write_text(json.dumps({"reversals": entries}), encoding="utf-8")
        return path

    def test_the_reviewed_list_and_the_code_must_name_the_same_rows(self, tmp_path: Path) -> None:
        R.load_reasons(self.write(tmp_path, [1, 2]), L.REVERSAL_1, [2, 1])
        with pytest.raises(P.PlanError, match="must agree"):
            R.load_reasons(self.write(tmp_path, [1]), L.REVERSAL_1, [1, 2])
        with pytest.raises(P.PlanError, match="must agree"):
            R.load_reasons(self.write(tmp_path, [1, 1]), L.REVERSAL_1, [1, 1])

    def test_a_missing_reasons_file_is_refused(self, tmp_path: Path) -> None:
        with pytest.raises(P.PlanError, match="the reviewed reasons are part of the plan"):
            R.load_reasons(tmp_path / "REASONS.json", L.REVERSAL_1, [1])

    @pytest.mark.parametrize("over", [{"quotes": []}, {"reason": ""}])
    def test_a_reversal_without_a_reason_or_evidence_is_refused(
        self, tmp_path: Path, over: dict[str, Any]
    ) -> None:
        """Without the refusal an empty quote list passes 'every quote verified' vacuously."""
        path = self.write(tmp_path, [1])
        raw = json.loads(path.read_text(encoding="utf-8"))
        raw["reversals"][0].update(over)
        path.write_text(json.dumps(raw), encoding="utf-8")
        with pytest.raises(P.PlanError, match="a reversal needs a reason and evidence"):
            R.load_reasons(path, L.REVERSAL_1, [1])

    def test_the_delivered_list_is_the_lane_s(self) -> None:
        reasons = R.load_reasons(
            A.lane_dir(L.REVERSAL_1) / "REASONS.json", L.REVERSAL_1, L.REVERSAL_1_JOURNAL_IDS
        )
        assert sorted(r.journal_id for r in reasons) == sorted(L.REVERSAL_1_JOURNAL_IDS)

    def test_the_delivered_plan_undoes_exactly_the_listed_rows(self) -> None:
        records = A.load_records(A.lane_dir(L.REVERSAL_1) / "PLAN.jsonl")
        A.validate_records(records, lane=L.REVERSAL_1)
        assert sorted(r.journal_id for r in records) == sorted(L.REVERSAL_1_JOURNAL_IDS)
        by_site = {r.site_id: (r.column, r.old_value, r.new_value) for r in records}
        assert by_site[AHIN] == ("country", "Pakistan", "Afghanistan")
        assert by_site[STANY] == ("period_start", "-2500", "-3000")
