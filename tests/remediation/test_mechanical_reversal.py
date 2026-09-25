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
        "change_key": "phase3:ahin",
        "evidence": [{"source": "wikidata:Q4695118", "quote": "P17 = Pakistan"}],
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
            "period_name": "1 - 500 AD",
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
        rereview=kw.get("rereview", {}),
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
            "SELECT id::text AS id, name, source_id, description, country::text AS country, "
            "period_start::text AS period_start, period_name::text AS period_name FROM unified_sites"
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
                    "period_name": "1 - 500 AD",
                }
            ]
        if sql.startswith("SELECT id, row_pk, column_name, run_stamp"):
            assert "column_name IN ('country')" in sql and f"row_pk IN ('{AHIN}')" in sql
            assert sql.endswith("ORDER BY id")
            return [{**entry(), "row_pk": AHIN}]
        raise AssertionError(f"unexpected statement: {sql[:80]!r}")


def test_load_state_reads_the_row_the_site_and_the_chain() -> None:
    production = Production()
    state = R.load_state(production, [reason()], L.REVERSAL_1)
    c = state[28384]
    assert c.live == "Pakistan" and [link.id for link in c.chain] == [28384]
    assert (c.site or {})["period_name"] == "1 - 500 AD", "the period pair is read for every site"
    assert "change_key, evidence FROM remediation_change_log" in production.sent[0]
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


# --------------------------------------------------------------------- the second list (2026-09-23)
BANWOL = "8cead41d-19f8-45cf-9dc0-144583641e4f"
CHANGE_KEY = "phase3:2b9daf737a30bf69496c92616bdc2110ab8549ce6bbd6f556f694e5520e9e07e"
WHY = "hand-read: the evidence's 57 BCE-938 CE is the Silla kingdom's span, not the palace's start"
NEW_REASON = "Both halves hold - the 57 BCE-938 CE span is the period of use of a Silla palace."


def rereview_row(**over: Any) -> dict[str, Any]:
    """One row of `REREVIEW_1_FINAL.jsonl`, as the re-review delivered it."""
    base = {
        "change_key": CHANGE_KEY,
        "batch_id": "batch-0031",
        "site_id": BANWOL,
        "site_name": "Banwolseong",
        "column": "period_start",
        "old_value": "1",
        "new_value": "-57",
        "decision": "reverse",
        "why": WHY,
        "new_reason": NEW_REASON,
        "new_refuted": False,
    }
    base.update(over)
    return base


def banwol_reason(**over: Any) -> R.Reason:
    base: dict[str, Any] = {
        "journal_id": 27924,
        "site_id": BANWOL,
        "name": "Banwolseong",
        "column": "period_start",
        "reason": "re-review 1 reverses it",
        "quotes": (R.Quote(f"rereview:{CHANGE_KEY}", "not the palace's start"),),
        "residual": "",
    }
    base.update(over)
    return R.Reason(**base)


def banwol_site(**over: Any) -> dict[str, Any]:
    base = {
        "id": BANWOL,
        "name": "Banwolseong",
        "source_id": "ancient_nerds",
        "description": "A Silla palace fortress.",
        "site_type": "Palace",
        "period_start": "-57",
        "period_name": "500 BC - 1 AD",
    }
    base.update(over)
    return base


def banwol_start(**over: Any) -> R.Cell:
    """The phase-3 write 27924 (period_start 1 -> -57), live and the last of its cell."""
    base: dict[str, Any] = {
        "entry": entry(
            id=27924,
            row_pk=BANWOL,
            column_name="period_start",
            old_value="1",
            new_value="-57",
            run_stamp="phase3:batch-0031:chunk-0001",
            test_id="P3/period_start",
            change_key=CHANGE_KEY,
        ),
        "site": banwol_site(),
        "chain": (P.JournalLink(27924, "phase3:batch-0031", "P3/period_start", "1", "-57"),),
        "live": "-57",
    }
    base.update(over)
    return R.Cell(**base)


LABEL_QUOTE = "period_start '1' -> '-57' - the write that left the label behind"


def banwol_label_reason(**over: Any) -> R.Reason:
    base: dict[str, Any] = {
        "journal_id": 30451,
        "site_id": BANWOL,
        "name": "Banwolseong",
        "column": "period_name",
        "reason": "the label follows the restored start",
        "quotes": (R.Quote("journal", LABEL_QUOTE),),
        "residual": "",
    }
    base.update(over)
    return R.Reason(**base)


def banwol_label(**over: Any) -> R.Cell:
    """The period-name lane's write 30451 ('1 - 500 AD' -> '500 BC - 1 AD'), derived from -57."""
    base: dict[str, Any] = {
        "entry": entry(
            id=30451,
            row_pk=BANWOL,
            column_name="period_name",
            old_value="1 - 500 AD",
            new_value="500 BC - 1 AD",
            run_stamp="2026-09-22_mechanical-period-name",
            test_id="P6/period-name-bucket",
            change_key=f"period-name-bucket:{BANWOL}",
            evidence=[
                {"source": "pipeline/utils/text.py:categorize_period", "quote": "(-57)"},
                {
                    "source": "remediation_change_log:27924",
                    "quote": f"phase3:batch-0031:chunk-0001 (P3/period_start): {LABEL_QUOTE}",
                },
            ],
        ),
        "site": banwol_site(),
        "chain": (
            P.JournalLink(
                30451,
                "2026-09-22_mechanical-period-name",
                "P6/period-name-bucket",
                "1 - 500 AD",
                "500 BC - 1 AD",
            ),
        ),
        "live": "500 BC - 1 AD",
    }
    base.update(over)
    return R.Cell(**base)


def decide2(r: R.Reason, c: R.Cell, rereview: dict[str, Any] | None = None) -> P.Verdict:
    return R.classify_reversal(
        r,
        c,
        lane=L.REVERSAL_2,
        pages={},
        gold={},
        rereview={CHANGE_KEY: rereview_row()} if rereview is None else rereview,
    )


class TestTheRereviewQuote:
    """A `rereview:<change_key>` quote stands only on the re-review row that decided to reverse
    exactly the write the journal row made."""

    def test_the_re_review_s_decision_to_reverse_is_the_evidence(self) -> None:
        v = decide2(banwol_reason(), banwol_start())
        assert v.ok and (v.old_value, v.new_value, v.journal_id) == ("-57", "1", 27924)
        quoted = next(e for e in v.evidence if e["source"] == f"rereview:{CHANGE_KEY}")
        assert quoted["url"] == R.REREVIEW_FILE

    def test_the_quote_may_come_from_the_reviewer_s_new_why(self) -> None:
        quotes = (R.Quote(f"rereview:{CHANGE_KEY}", "period of use of a Silla palace"),)
        assert decide2(banwol_reason(quotes=quotes), banwol_start()).ok

    @pytest.mark.parametrize(
        ("row", "problem"),
        [
            (None, "is not a row of the re-review"),
            (rereview_row(decision="keep"), "decided 'keep'"),
            (rereview_row(change_key="phase3:another"), "decided"),
            (rereview_row(old_value="-500"), "journal row 27924 wrote"),
            (rereview_row(new_value="-300"), "journal row 27924 wrote"),
            (rereview_row(column="site_type"), "journal row 27924 wrote"),
            (rereview_row(site_id=STANY), "journal row 27924 wrote"),
        ],
    )
    def test_a_re_review_row_that_did_not_reverse_this_write_refuses(
        self, row: dict[str, Any] | None, problem: str
    ) -> None:
        v = decide2(banwol_reason(), banwol_start(), {} if row is None else {CHANGE_KEY: row})
        assert (v.ok, v.reason) == (False, "evidence-not-found") and problem in v.note

    def test_the_quote_must_be_in_the_re_review_s_words(self) -> None:
        quotes = (R.Quote(f"rereview:{CHANGE_KEY}", "the palace was founded in 57 BCE"),)
        v = decide2(banwol_reason(quotes=quotes), banwol_start())
        assert (v.reason, v.note) == (
            "evidence-not-found",
            f"'the palace was founded in 57 BCE' is not in rereview:{CHANGE_KEY}",
        )

    def test_the_re_review_file_is_read_by_change_key_once_each(self, tmp_path: Path) -> None:
        path = tmp_path / R.REREVIEW_FILE
        path.write_text(json.dumps(rereview_row()) + "\n", encoding="utf-8")
        assert R.load_rereview(path) == {CHANGE_KEY: rereview_row()}
        path.write_text((json.dumps(rereview_row()) + "\n") * 2, encoding="utf-8")
        with pytest.raises(P.PlanError, match="decides .* twice"):
            R.load_rereview(path)
        with pytest.raises(P.PlanError, match="the re-review a quote cites is part of the plan"):
            R.load_rereview(tmp_path / "missing.jsonl")

    def test_only_a_list_that_cites_the_re_review_needs_it(self) -> None:
        assert R.cites_the_rereview([banwol_reason()])
        assert not R.cites_the_rereview([reason(), banwol_label_reason()])


class TestTheJournalQuote:
    def test_the_undone_row_s_own_evidence_is_quoted(self) -> None:
        v = decide2(banwol_label_reason(), banwol_label())
        assert v.ok and v.new_value == "1 - 500 AD"
        assert {"source": "journal", "url": "remediation_change_log.evidence"}.items() <= next(
            e for e in v.evidence if e["source"] == "journal"
        ).items()

    def test_a_quote_the_row_s_evidence_does_not_hold_refuses(self) -> None:
        quotes = (R.Quote("journal", "period_start '1' -> '-300'"),)
        v = decide2(banwol_label_reason(quotes=quotes), banwol_label())
        assert v.reason == "evidence-not-found"

    def test_a_journal_row_without_evidence_refuses(self) -> None:
        cell = banwol_label(entry={**banwol_label().entry, "evidence": None})  # type: ignore[dict-item]
        v = decide2(banwol_label_reason(), cell)
        assert (v.reason, v.note) == ("evidence-not-found", "journal row 30451 carries no evidence")

    def test_a_journal_quote_names_no_other_row(self) -> None:
        quotes = (R.Quote("journal:27924", LABEL_QUOTE),)
        v = decide2(banwol_label_reason(quotes=quotes), banwol_label())
        assert v.note == "'journal:27924' is not a source this lane can check"


def plan2(
    reasons: list[R.Reason], cells: dict[int, R.Cell], rereview: dict[str, Any] | None = None
) -> P.Plan:
    return R.build_reversal_plan(
        reasons,
        cells,
        lane=L.REVERSAL_2,
        pages={},
        gold={},
        rereview={CHANGE_KEY: rereview_row()} if rereview is None else rereview,
        built_at="t",
    )


class TestThePeriodLabel:
    """`period_name` stays the bucket of `period_start` through a reversal (`keep_the_period_label`)."""

    def test_a_start_and_its_label_go_back_together(self) -> None:
        plan = plan2(
            [banwol_reason(), banwol_label_reason()],
            {27924: banwol_start(), 30451: banwol_label()},
        )
        assert {(c.column, c.new_value) for c in plan.changes} == {
            ("period_start", "1"),
            ("period_name", "1 - 500 AD"),
        }
        label = next(c for c in plan.changes if c.column == "period_name")
        assert label.evidence[-1]["quote"] == (
            "categorize_period(1) = '1 - 500 AD' - the period_start the site is left with"
        )

    def test_a_start_that_would_leave_its_label_behind_is_refused(self) -> None:
        plan = plan2([banwol_reason()], {27924: banwol_start()})
        (refused,) = plan.skipped
        assert (refused.reason, refused.column, plan.changes) == (
            "period-name-left-behind",
            "period_start",
            (),
        )
        assert "'1 - 500 AD'" in refused.note and "'500 BC - 1 AD'" in refused.note

    def test_a_label_whose_start_is_not_restored_is_refused(self) -> None:
        plan = plan2([banwol_label_reason()], {30451: banwol_label()})
        (refused,) = plan.skipped
        assert (refused.reason, plan.changes) == ("period-name-not-the-bucket", ())

    def test_a_refused_start_takes_its_label_with_it(self) -> None:
        """The start's own evidence fails, so the label - derived from it - must not move."""
        plan = plan2(
            [banwol_reason(), banwol_label_reason()],
            {27924: banwol_start(), 30451: banwol_label()},
            rereview={CHANGE_KEY: rereview_row(decision="keep")},
        )
        assert not plan.changes
        assert {(s.column, s.reason) for s in plan.skipped} == {
            ("period_start", "evidence-not-found"),
            ("period_name", "period-name-not-the-bucket"),
        }

    def test_a_refused_label_takes_its_start_with_it(self) -> None:
        wrong = banwol_label(
            entry={**banwol_label().entry, "old_value": "500 - 1000 AD"},  # type: ignore[dict-item]
            chain=(P.JournalLink(30451, "p", "t", "500 - 1000 AD", "500 BC - 1 AD"),),
        )
        plan = plan2(
            [banwol_reason(), banwol_label_reason()], {27924: banwol_start(), 30451: wrong}
        )
        assert not plan.changes
        assert {(s.column, s.reason) for s in plan.skipped} == {
            ("period_name", "period-name-not-the-bucket"),
            ("period_start", "period-name-left-behind"),
        }

    def test_a_start_within_its_bucket_needs_no_label(self) -> None:
        """Reversal 1's two starts stay in '3000 - 1500 BC': nothing to carry along."""
        site = banwol_site(period_start="-2500", period_name="3000 - 1500 BC")
        cell = banwol_start(
            entry={**banwol_start().entry, "old_value": "-3000", "new_value": "-2500"},  # type: ignore[dict-item]
            chain=(P.JournalLink(27924, "p", "t", "-3000", "-2500"),),
            live="-2500",
            site=site,
        )
        row = rereview_row(old_value="-3000", new_value="-2500")
        plan = plan2([banwol_reason()], {27924: cell}, rereview={CHANGE_KEY: row})
        assert [(c.column, c.new_value) for c in plan.changes] == [("period_start", "-3000")]

    def test_a_label_that_was_not_the_bucket_before_does_not_hold_the_start(self) -> None:
        """The list does not break a pair that was broken before it: that is the period-name
        lane's residual, not a reason to keep a reversed write."""
        site = banwol_site(period_name="> 1500 AD")
        plan = plan2([banwol_reason()], {27924: banwol_start(site=site)})
        assert [(c.column, c.new_value) for c in plan.changes] == [("period_start", "1")]


class TestTheCli:
    def test_the_lane_is_named_and_must_be_a_reversal_lane(
        self, capsys: pytest.CaptureFixture
    ) -> None:
        with pytest.raises(SystemExit):
            R.main(["--write"])
        with pytest.raises(SystemExit):
            R.main(["--lane", "scope-e4", "--write"])
        assert "invalid choice" in capsys.readouterr().err

    def test_write_plans_a_rereview_quoted_list_from_the_lane_s_copy(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """`--write` reads the re-review copy in the lane directory when a quote cites it."""
        entries = [
            {
                "journal_id": 27924,
                "site_id": BANWOL,
                "name": "Banwolseong",
                "column": "period_start",
                "reason": "re-review 1 reverses it",
                "quotes": [{"source": f"rereview:{CHANGE_KEY}", "text": "not the palace's start"}],
            },
            {
                "journal_id": 30451,
                "site_id": BANWOL,
                "name": "Banwolseong",
                "column": "period_name",
                "reason": "the label follows the restored start",
                "quotes": [{"source": "journal", "text": LABEL_QUOTE}],
            },
        ]
        (tmp_path / "REASONS.json").write_text(json.dumps({"reversals": entries}), encoding="utf-8")
        (tmp_path / R.REREVIEW_FILE).write_text(json.dumps(rereview_row()), encoding="utf-8")
        (tmp_path / "export").mkdir()
        (tmp_path / "export" / "pages.json").write_text('{"pages": {}}', encoding="utf-8")
        start, label = banwol_start(), banwol_label()

        def reader(sql: str) -> list[dict[str, Any]]:
            if sql.startswith("SELECT id, row_pk, table_name"):
                return [dict(start.entry or {}), dict(label.entry or {})]
            if sql.startswith("SELECT id::text AS id"):
                return [banwol_site()]
            return [
                {"row_pk": BANWOL, "column_name": c, **vars(link)}
                for c, cell in (("period_start", start), ("period_name", label))
                for link in cell.chain
            ]

        monkeypatch.setattr(R, "REVERSAL_LISTS", {L.REVERSAL_2.name: (27924, 30451)})
        monkeypatch.setattr(R, "psql_json_reader", lambda: reader)
        assert R.main(["--lane", L.REVERSAL_2.name, "--out", str(tmp_path), "--write"]) == 0
        records = A.load_records(tmp_path / "PLAN.jsonl")
        assert {(r.column, r.new_value) for r in records} == {
            ("period_start", "1"),
            ("period_name", "1 - 500 AD"),
        }


class TestTheDeliveredSecondList:
    DIR = A.lane_dir(L.REVERSAL_2)

    def rows(self) -> list[dict[str, Any]]:
        text = (self.DIR / R.REREVIEW_FILE).read_text(encoding="utf-8")
        return [json.loads(line) for line in text.splitlines()]

    def test_the_list_is_every_reverse_row_of_the_re_review_and_its_labels(self) -> None:
        rows = self.rows()
        assert len(rows) == 77 and sum(r["decision"] == "reverse" for r in rows) == 45
        reasons = R.load_reasons(
            self.DIR / "REASONS.json", L.REVERSAL_2, L.REVERSAL_LISTS[L.REVERSAL_2.name]
        )
        cited = {
            q.source.partition(":")[2]
            for r in reasons
            for q in r.quotes
            if q.source.startswith("rereview:")
        }
        assert cited == {r["change_key"] for r in rows if r["decision"] == "reverse"}
        labels = [r for r in reasons if r.column == "period_name"]
        assert len(labels) == 8 and all(q.source == "journal" for r in labels for q in r.quotes)

    def test_the_trundle_is_reversed_and_its_field_stays_open(self) -> None:
        reasons = R.load_reasons(
            self.DIR / "REASONS.json", L.REVERSAL_2, L.REVERSAL_LISTS[L.REVERSAL_2.name]
        )
        (trundle,) = [r for r in reasons if r.name == "The Trundle" and r.column == "period_start"]
        assert "c. 3500 BC" in trundle.residual

    def test_the_delivered_plan_keeps_every_period_label_the_bucket_of_its_start(self) -> None:
        records = A.load_records(self.DIR / "PLAN.jsonl")
        A.validate_records(records, lane=L.REVERSAL_2)
        assert sorted(r.journal_id for r in records) == sorted(L.REVERSAL_2_JOURNAL_IDS)
        starts = {r.site_id: r.new_value for r in records if r.column == "period_start"}
        from pipeline.utils.text import categorize_period

        for label in (r for r in records if r.column == "period_name"):
            assert label.new_value == categorize_period(int(starts[label.site_id]))


def test_the_second_list_reads_back_the_period_pair_and_its_own_residual() -> None:
    """After the apply: no cell still holds a value the list undoes, and no curated row's label
    left its start's bucket (the period-name lane's residual, read before and after)."""
    readback = L.REVERSAL_2_READBACK
    assert L.REVERSAL_2.post_commit_residual.metric in readback
    assert "curated rows whose period_name is not the bucket of period_start" in readback
    assert "journal rows of this list that a later write superseded" in readback
    assert L.REVERSAL_2_READBACK.count("30536") == 2, "the residual and the superseded count"


def test_the_reversal_residual_says_it_counts_sites() -> None:
    """The residual is a `FROM unified_sites WHERE ...` predicate: it counts sites, not cells.
    Read on production 2026-09-23: 45 for the second list's 53 cells, which sit on 45 sites (8
    carry a start and its label) - a metric named for cells would read as 8 cells missing."""
    for lane in (L.REVERSAL_1, L.REVERSAL_2):
        assert lane.post_commit_residual.metric == (
            "curated sites still holding a value this reversal list undoes"
        )


# ------------------------------------------------------------ the third list (2026-09-25): the Opus audit
MARAY = "0d8b0d61-6c1e-4b8a-9d59-0b8e1a2f3c4d"
OPUS_KEY = "phase3:" + "3" * 64
OPUS_EVIDENCE = "output/remediation/phase3_runner/runs/mass/batch-0010/evidence/maray%2Fenwiki.txt"
P1_QUOTE = "Marayniyoq is an archaeological site in Peru."
TIE_QUOTES = ("the old value is not refuted", "an Inca settlement on a hill")
KEEP_QUOTE = "archaeological site in the Cusco Region"


def opus_verdict(name: str, *quotes: str) -> dict[str, Any]:
    return {
        "change_key": OPUS_KEY,
        "verdict": name,
        "right_value": None,
        "reason": f"{name} because",
        "quotes": [{"source": OPUS_EVIDENCE, "quote": q} for q in quotes],
    }


def opus_line(**over: Any) -> dict[str, Any]:
    """One DECISIONS.jsonl line of the Opus re-verification: p1 revert, p2 keep, tie revert."""

    def check(*outcomes: str) -> dict[str, Any]:
        return {
            "counted": all(o == "found" for o in outcomes),
            "reason": "",
            "quotes": [{"source": OPUS_EVIDENCE, "outcome": o, "detail": ""} for o in outcomes],
        }

    base: dict[str, Any] = {
        "change_key": OPUS_KEY,
        "site_id": MARAY,
        "site_name": "Marayniyoq",
        "column": "site_type",
        "old_value": "City/town/settlement",
        "written_value": "Archaeological site",
        "decision": "revert",
        "reversal": True,
        "basis": [
            {"pass": "p1", "verdict": "revert", "counted": True, "from": "VERDICTS_RAW.json p1"},
            {
                "pass": "p2",
                "verdict": "keep",
                "counted": True,
                "from": "VERDICTS_ROUND2.json sample",
            },
            {
                "pass": "tie",
                "verdict": "revert",
                "counted": True,
                "from": "VERDICTS_ROUND3.json tie",
            },
        ],
        "quote_check": {"p1": check("found"), "p2": check("found"), "tie": check("found", "found")},
    }
    base.update(over)
    return base


def write_opus(tmp_path: Path, *lines: dict[str, Any]) -> Path:
    """An opus_audit directory: DECISIONS.jsonl and the verdict files its lines name."""
    audit = tmp_path / "opus_audit"
    audit.mkdir(exist_ok=True)
    (audit / "DECISIONS.jsonl").write_text(
        "".join(json.dumps(line) + "\n" for line in lines), encoding="utf-8"
    )
    files = {
        "VERDICTS_RAW.json": {"p1": {OPUS_KEY: opus_verdict("revert", P1_QUOTE)}},
        "VERDICTS_ROUND2.json": {"sample": {OPUS_KEY: opus_verdict("keep", KEEP_QUOTE)}},
        "VERDICTS_ROUND3.json": {"tie": {OPUS_KEY: opus_verdict("revert", *TIE_QUOTES)}},
    }
    for name, content in files.items():
        (audit / name).write_text(json.dumps(content), encoding="utf-8")
    return audit


def maray_reason(**over: Any) -> R.Reason:
    base: dict[str, Any] = {
        "journal_id": 28200,
        "site_id": MARAY,
        "name": "Marayniyoq",
        "column": "site_type",
        "reason": "the Opus re-verification decided to revert this write",
        "quotes": (R.Quote(f"opus:{OPUS_KEY}", TIE_QUOTES[1]),),
        "residual": "The field is open again, not corrected.",
    }
    base.update(over)
    return R.Reason(**base)


def maray_cell(**over: Any) -> R.Cell:
    """The phase-3 write 28200 (site_type City/town/settlement -> Archaeological site), live."""
    base: dict[str, Any] = {
        "entry": entry(
            id=28200,
            row_pk=MARAY,
            column_name="site_type",
            old_value="City/town/settlement",
            new_value="Archaeological site",
            run_stamp="phase3:batch-0010:chunk-0001",
            test_id="P3/site_type",
            change_key=OPUS_KEY,
        ),
        "site": {
            "id": MARAY,
            "name": "Marayniyoq",
            "source_id": "ancient_nerds",
            "description": "An Inca site.",
            "site_type": "Archaeological site",
            "period_start": "1400",
            "period_name": "1000 - 1500 AD",
            "country": "Peru",
        },
        "chain": (
            P.JournalLink(
                28200,
                "phase3:batch-0010",
                "P3/site_type",
                "City/town/settlement",
                "Archaeological site",
            ),
        ),
        "live": "Archaeological site",
    }
    base.update(over)
    return R.Cell(**base)


def decide3(r: R.Reason, c: R.Cell, opus: dict[str, Any]) -> P.Verdict:
    return R.classify_reversal(r, c, lane=L.REVERSAL_3, pages={}, gold={}, rereview={}, opus=opus)


class TestTheOpusQuote:
    """An `opus:<change_key>` quote stands only on the Opus re-verification's decision to revert
    exactly the write the journal row made, and only in the quotes of the verdicts that decided it,
    each found by the audit's own machine quote check."""

    def test_the_audits_decision_to_revert_is_the_evidence(self, tmp_path: Path) -> None:
        opus = R.load_opus(write_opus(tmp_path, opus_line()))
        v = decide3(maray_reason(), maray_cell(), opus)
        assert v.ok and (v.old_value, v.new_value, v.journal_id) == (
            "Archaeological site",
            "City/town/settlement",
            28200,
        )
        quoted = next(e for e in v.evidence if e["source"] == f"opus:{OPUS_KEY}")
        assert quoted == {
            "source": f"opus:{OPUS_KEY}",
            "url": R.OPUS_URL,
            "quote": TIE_QUOTES[1],
        }

    def test_the_text_is_the_found_quotes_of_the_verdicts_that_decided_to_revert(
        self, tmp_path: Path
    ) -> None:
        opus = R.load_opus(write_opus(tmp_path, opus_line()))
        assert opus[OPUS_KEY].quotes == (P1_QUOTE, *TIE_QUOTES)
        for text in (P1_QUOTE, *TIE_QUOTES):
            assert decide3(
                maray_reason(quotes=(R.Quote(f"opus:{OPUS_KEY}", text),)), maray_cell(), opus
            ).ok

    @pytest.mark.parametrize(
        "text",
        [KEEP_QUOTE, "Marayniyoq was a town", "archaeological site in Serbia"],
        ids=["the keep's quote", "a paraphrase", "another row's line"],
    )
    def test_a_quote_the_deciding_verdicts_do_not_carry_refuses(
        self, tmp_path: Path, text: str
    ) -> None:
        opus = R.load_opus(write_opus(tmp_path, opus_line()))
        v = decide3(maray_reason(quotes=(R.Quote(f"opus:{OPUS_KEY}", text),)), maray_cell(), opus)
        assert (v.ok, v.reason, v.note) == (
            False,
            "evidence-not-found",
            f"{text!r} is not in opus:{OPUS_KEY}",
        )

    @pytest.mark.parametrize(
        ("line", "problem"),
        [
            (None, "is not a row of the Opus re-verification"),
            (opus_line(decision="keep", reversal=False), "decided 'keep'"),
            (opus_line(decision="pending", reversal=False), "decided 'pending'"),
            (opus_line(reversal=False), "decided 'revert'"),
            (opus_line(site_id=AHIN), "journal row 28200 wrote"),
            (opus_line(column="period_start"), "journal row 28200 wrote"),
            (opus_line(old_value="Settlement"), "journal row 28200 wrote"),
            (opus_line(written_value="Temple"), "journal row 28200 wrote"),
        ],
        ids=[
            "no line",
            "keep",
            "pending",
            "superseded",
            "another site",
            "another column",
            "another old value",
            "another written value",
        ],
    )
    def test_a_decision_that_did_not_revert_this_write_refuses(
        self, tmp_path: Path, line: dict[str, Any] | None, problem: str
    ) -> None:
        opus = {} if line is None else R.load_opus(write_opus(tmp_path, line))
        v = decide3(maray_reason(), maray_cell(), opus)
        assert (v.ok, v.reason) == (False, "evidence-not-found") and problem in v.note

    def test_a_decision_on_another_write_of_the_same_cell_refuses(self) -> None:
        """The quote names the audit's row by change_key: another key's decision is no decision on
        this journal row's write, whatever cell and values it names."""
        other = "phase3:" + "4" * 64
        opus = {
            other: R.OpusDecision(
                change_key=other,
                site_id=MARAY,
                column="site_type",
                old_value="City/town/settlement",
                written_value="Archaeological site",
                decision="revert",
                reversal=True,
                quotes=(TIE_QUOTES[1],),
            )
        }
        quotes = (R.Quote(f"opus:{other}", TIE_QUOTES[1]),)
        v = decide3(maray_reason(quotes=quotes), maray_cell(), opus)
        assert (v.ok, v.reason) == (False, "evidence-not-found")
        assert "journal row 28200 wrote" in v.note

    def test_a_verdict_that_does_not_count_carries_no_quote(self, tmp_path: Path) -> None:
        line = opus_line()
        line["basis"][2]["counted"] = False
        assert R.load_opus(write_opus(tmp_path, line))[OPUS_KEY].quotes == (P1_QUOTE,)

    def test_a_quote_the_audits_check_did_not_find_is_none(self, tmp_path: Path) -> None:
        line = opus_line()
        line["quote_check"]["tie"]["quotes"][0]["outcome"] = "not found"
        assert R.load_opus(write_opus(tmp_path, line))[OPUS_KEY].quotes == (
            P1_QUOTE,
            TIE_QUOTES[1],
        )

    def test_a_basis_the_verdict_file_does_not_hold_is_refused(self, tmp_path: Path) -> None:
        line = opus_line()
        line["basis"][0]["verdict"] = "wrong-both"
        with pytest.raises(P.PlanError, match="VERDICTS_RAW.json p1 holds 'revert'"):
            R.load_opus(write_opus(tmp_path, line))
        line = opus_line()
        line["basis"][2]["from"] = "VERDICTS_ROUND3.json second"
        with pytest.raises(P.PlanError, match="no verdict"):
            R.load_opus(write_opus(tmp_path, line))

    @pytest.mark.parametrize("origin", ["../INPUT.jsonl p1", "VERDICTS_RAWS.json p1", "p1"])
    def test_a_basis_names_a_verdict_file_of_the_audit_only(
        self, tmp_path: Path, origin: str
    ) -> None:
        line = opus_line()
        line["basis"][0]["from"] = origin
        with pytest.raises(P.PlanError, match="not a verdict file"):
            R.load_opus(write_opus(tmp_path, line))

    def test_the_quote_check_must_be_the_verdicts_own(self, tmp_path: Path) -> None:
        line = opus_line()
        line["quote_check"]["tie"]["quotes"] = line["quote_check"]["tie"]["quotes"][:1]
        with pytest.raises(P.PlanError, match="quote check"):
            R.load_opus(write_opus(tmp_path, line))

    def test_the_decisions_file_is_read_by_change_key_once_each(self, tmp_path: Path) -> None:
        with pytest.raises(P.PlanError, match="decides .* twice"):
            R.load_opus(write_opus(tmp_path, opus_line(), opus_line()))
        with pytest.raises(P.PlanError, match="the Opus re-verification a quote cites"):
            R.load_opus(tmp_path / "missing")

    def test_only_a_list_that_cites_the_opus_audit_needs_it(self) -> None:
        assert R.cites_the_opus_audit([maray_reason()])
        assert not R.cites_the_opus_audit([reason(), banwol_reason(), banwol_label_reason()])


class TestTheThirdLane:
    def test_the_lane_writes_every_column_the_audit_reverts_and_the_labels(self) -> None:
        assert set(L.REVERSAL_3.columns) == {"site_type", "period_start", "period_name", "country"}
        assert (
            L.REVERSAL_3.reverses_journal
            and L.REVERSAL_3.cell("period_start").sql_type == "integer"
        )
        assert L.LANES[L.REVERSAL_3.name] is L.REVERSAL_3
        assert L.REVERSAL_LISTS[L.REVERSAL_3.name] == L.REVERSAL_3_JOURNAL_IDS
        assert A.lane_dir(L.REVERSAL_3).name == "mechanical_reversal_3"
        stamps = {lane.run_stamp for lane in L.LANES.values()}
        assert len(stamps) == len(L.LANES), "every lane journals under its own stamp"

    def test_the_lane_reads_back_its_residual_the_period_pair_and_the_card_country(self) -> None:
        readback = L.LANE_READBACKS[L.REVERSAL_3.name]
        assert L.REVERSAL_3.post_commit_residual.metric in readback
        assert "journal rows of this list that a later write superseded" in readback
        assert "curated rows whose period_name is not the bucket of period_start" in readback
        assert "card_stats rows whose civilization differs from the site country" in readback
        assert L.REVERSAL_3.post_commit_residual.metric == (
            "curated sites still holding a value this reversal list undoes"
        )

    def test_a_start_the_audit_reverts_and_its_label_go_back_together(self, tmp_path: Path) -> None:
        """Banwolseong's start 1 -> -57, reverted by the audit, with the period-name lane's label."""
        line = opus_line(
            change_key=CHANGE_KEY,
            site_id=BANWOL,
            column="period_start",
            old_value="1",
            written_value="-57",
        )
        audit = write_opus(tmp_path, line)
        for name in ("VERDICTS_RAW.json", "VERDICTS_ROUND2.json", "VERDICTS_ROUND3.json"):
            path = audit / name
            path.write_text(path.read_text(encoding="utf-8").replace(OPUS_KEY, CHANGE_KEY), "utf-8")
        start = banwol_reason(quotes=(R.Quote(f"opus:{CHANGE_KEY}", P1_QUOTE),))
        plan = R.build_reversal_plan(
            [start, banwol_label_reason()],
            {27924: banwol_start(), 30451: banwol_label()},
            lane=L.REVERSAL_3,
            pages={},
            gold={},
            rereview={},
            opus=R.load_opus(audit),
            built_at="t",
        )
        assert {(c.column, c.new_value) for c in plan.changes} == {
            ("period_start", "1"),
            ("period_name", "1 - 500 AD"),
        }
        assert plan.skipped == ()

    def test_write_plans_an_opus_quoted_list_from_the_audit_files(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        audit = write_opus(tmp_path, opus_line())
        out = tmp_path / "lane"
        (out / "export").mkdir(parents=True)
        (out / "export" / "pages.json").write_text('{"pages": {}}', encoding="utf-8")
        entries = [
            {
                "journal_id": 28200,
                "site_id": MARAY,
                "name": "Marayniyoq",
                "column": "site_type",
                "reason": "the Opus re-verification decided to revert this write",
                "quotes": [{"source": f"opus:{OPUS_KEY}", "text": TIE_QUOTES[0]}],
            }
        ]
        (out / "REASONS.json").write_text(json.dumps({"reversals": entries}), encoding="utf-8")
        c = maray_cell()

        def reader(sql: str) -> list[dict[str, Any]]:
            if sql.startswith("SELECT id, row_pk, table_name"):
                return [dict(c.entry or {})]
            if sql.startswith("SELECT id::text AS id"):
                return [dict(c.site or {})]
            return [{"row_pk": MARAY, "column_name": "site_type", **vars(link)} for link in c.chain]

        monkeypatch.setattr(R, "REVERSAL_LISTS", {L.REVERSAL_3.name: (28200,)})
        monkeypatch.setattr(R, "psql_json_reader", lambda: reader)
        monkeypatch.setattr(R, "OPUS_AUDIT", audit)
        assert R.main(["--lane", L.REVERSAL_3.name, "--out", str(out), "--write"]) == 0
        (record,) = A.load_records(out / "PLAN.jsonl")
        assert (record.column, record.old_value, record.new_value, record.journal_id) == (
            "site_type",
            "Archaeological site",
            "City/town/settlement",
            28200,
        )
        assert any(e["source"] == f"opus:{OPUS_KEY}" for e in record.evidence)
