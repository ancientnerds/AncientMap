"""WD1's seeds (`scripts/remediation/fields/seeds.py`): the fields earlier readings found wrong.

Pinned: a counted stage-1 WRONG verdict on a WD1 field becomes a seed and a `period_name` verdict
asks `period_start`; a planted canary, a CORRECT verdict, an uncounted one and a field WD1 does not
answer do not; B13 takes exactly the two wrong-both reasons; the file written is the one the
classification reads.
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

from fields import classify as C  # noqa: E402
from fields import seeds as S  # noqa: E402

A_ID = "0025b0ba-fd74-4c08-96e3-acc17956aa44"
B_ID = "786cada5-1feb-4c5c-9e79-b8ffdf8aacc6"


def verdict(site_id: str, field: str, value: str | None, *, right: Any = None) -> dict[str, Any]:
    answer = {
        "verdict": "WRONG",
        "reasoning": "The cairn stands 2 km  north.",
        "right_value": right,
    }
    return {
        "label": f"q-{site_id[:4]}-{field}",
        "site_id": site_id,
        "field": field,
        "stage": "s1",
        "final": None if value is None else {"attempt": 1, "verdict": value, "via": "counted"},
        "attempts": [
            {"answer": {**answer, "verdict": "CORRECT"}, "counted": False},
            {"answer": {**answer, "verdict": value or "WRONG"}, "counted": True},
        ],
    }


def skipped(site_id: str, column: str, reason: str) -> dict[str, Any]:
    return {"site_id": site_id, "column": column, "reason": reason, "proposed_value": "-2500",
            "note": "2 counted quote(s) state '-2500', but none in text about the site"}  # fmt: skip


class TestStageOne:
    def test_a_counted_wrong_verdict_on_a_wd1_field_is_a_seed(self) -> None:
        rows = [
            verdict(A_ID, "coordinates", "WRONG", right="56.1, -5.4"),
            verdict(A_ID, "period_name", "WRONG"),
            verdict(B_ID, "coordinates", "WRONG"),  # a planted canary
            verdict(B_ID, "site_type", "CORRECT"),
            verdict(B_ID, "source_url", None),  # never counted
            verdict(B_ID, "description", "WRONG"),  # not a WD1 field
        ]
        seeds = S.stage1_seeds(rows, [{"site_id": B_ID, "field": "coordinates"}])
        assert [(s["site_id"], s["field"]) for s in seeds] == [
            (A_ID, "coordinates"),
            (A_ID, "period_start"),
        ]
        assert seeds[0]["finding"] == (
            "an independent Opus check judged the stored coordinates WRONG (it proposed "
            "'56.1, -5.4'): The cairn stands 2 km north."
        )
        assert "stored period_name WRONG" in seeds[1]["finding"]

    def test_a_final_verdict_that_is_not_its_counted_attempt_s_is_refused(self) -> None:
        row = verdict(A_ID, "site_type", "WRONG")
        row["attempts"][1]["counted"] = False
        with pytest.raises(S.SeedError, match="not its counted attempt"):
            S.stage1_seeds([row], [])

    def test_a_long_finding_is_clipped(self) -> None:
        row = verdict(A_ID, "site_type", "WRONG")
        row["attempts"][1]["answer"]["reasoning"] = "x" * 2000
        finding = S.stage1_seeds([row], [])[0]["finding"]
        assert len(finding) == S.FINDING_CHARS and finding.endswith("...")


class TestWrongBoth:
    def test_only_the_two_open_reasons_are_seeds(self) -> None:
        rows = [
            skipped(A_ID, "period_start", "no-verbatim-evidence"),
            skipped(A_ID, "site_type", "judges-disagree"),
            skipped(B_ID, "site_type", "not-reverted"),
            skipped(B_ID, "country", "not-restored-by-journal-reversal-3"),
        ]
        seeds = S.wrong_both_seeds(rows)
        assert [(s["field"], s["source"]) for s in seeds] == [
            ("period_start", S.WRONG_BOTH_SOURCE),
            ("site_type", S.WRONG_BOTH_SOURCE),
        ]
        assert "proposed '-2500'" in seeds[0]["finding"]

    def test_an_open_cell_on_another_column_is_refused(self) -> None:
        with pytest.raises(S.SeedError, match="not a WD1 field"):
            S.wrong_both_seeds([skipped(A_ID, "country", "judges-disagree")])


def test_the_file_written_is_the_one_the_classification_reads(tmp_path: Path) -> None:
    stage1 = tmp_path / "draw"
    (stage1 / "judging").mkdir(parents=True)
    (stage1 / "judging" / "STAGE1.jsonl").write_text(
        json.dumps(verdict(B_ID, "site_type", "WRONG")) + "\n", encoding="utf-8"
    )
    (stage1 / "CANARIES.jsonl").write_text("", encoding="utf-8")
    both = tmp_path / "SKIPPED.jsonl"
    both.write_text(
        json.dumps(skipped(A_ID, "period_start", "judges-disagree")) + "\n", encoding="utf-8"
    )
    result = S.build(tmp_path / "run", stage1_dir=stage1, wrong_both=both)
    assert result["seeds"] == 2 and result["sites"] == 2
    seeds = C.read_seeds(tmp_path / "run")
    assert set(seeds) == {A_ID, B_ID}
    assert seeds[A_ID]["period_start"][0].startswith(S.WRONG_BOTH_SOURCE + ": two Opus readings")
    with pytest.raises(S.SeedError, match="is missing"):
        S.build(tmp_path / "run", stage1_dir=tmp_path / "nowhere", wrong_both=both)
