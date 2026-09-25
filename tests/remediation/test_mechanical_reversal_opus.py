"""journal-reversal-3's list, built from the Opus re-verification's reversal input.

`reversal_opus.build_list` is pure: the journal rows and the period-name labels are given to it. The
readers are driven by a stand-in for production that answers only the statements they send, and
checks that each names the rows it must.
"""

from __future__ import annotations

import ast
import hashlib
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
from mechanical import plan as P  # noqa: E402
from mechanical import reversal as R  # noqa: E402
from mechanical import reversal_opus as O  # noqa: E402

TYPE_KEY = "phase3:" + "a" * 64
START_KEY = "phase3:" + "b" * 64
SAME_KEY = "phase3:" + "c" * 64
MARAY = "0d8b0d61-6c1e-4b8a-9d59-0b8e1a2f3c4d"
TRUNDLE = "05ee235c-2ded-4af5-9e94-980c7750bc52"
DOLNI = "7a1c2e3f-4b5d-4e6f-8a9b-0c1d2e3f4a5b"
LEFT_BEHIND = "phase3:batch-0260:chunk-0001 (P3/period_start): period_start '-1000' -> '-500' - the write that left the label behind"


def line(key: str, site: str, name: str, column: str, old: str, new: str) -> dict[str, Any]:
    """One REVERSAL_3_INPUT.jsonl line, as `opus_audit.decide.reversal_input` writes it."""
    return {
        "journal_id": None,
        "change_key": key,
        "site_id": site,
        "name": name,
        "column": column,
        "old_value": old,
        "new_value": new,
        "reason": "the Opus re-verification decided to revert this write: p1 revert, p2 revert",
        "quotes": [
            {"source": "output/remediation/x%2Fenwiki.txt", "text": f"{name} one"},
            {"source": "https://example.org/page", "text": f"{name} two"},
        ],
        "residual": "The field is open again, not corrected.",
        "judges": [],
    }


ROWS = [
    line(TYPE_KEY, MARAY, "Marayniyoq", "site_type", "City/town/settlement", "Archaeological site"),
    line(START_KEY, TRUNDLE, "The Trundle", "period_start", "-1000", "-500"),
    line(SAME_KEY, DOLNI, "Dolni Glavanak Cromlech", "period_start", "-1500", "-800"),
]


def journal_row(i: int, r: dict[str, Any], **over: Any) -> dict[str, Any]:
    base = {
        "id": i,
        "change_key": r["change_key"],
        "table_name": "unified_sites",
        "column_name": r["column"],
        "row_pk": r["site_id"],
        "old_value": r["old_value"],
        "new_value": r["new_value"],
    }
    base.update(over)
    return base


JOURNAL = {
    TYPE_KEY: [journal_row(28200, ROWS[0])],
    START_KEY: [journal_row(29246, ROWS[1])],
    SAME_KEY: [journal_row(29001, ROWS[2])],
}


def label_row(i: int, site: str, cites: int, **over: Any) -> dict[str, Any]:
    """A period-name lane row whose evidence names the start write that left the label behind."""
    base = {
        "id": i,
        "row_pk": site,
        "run_stamp": "2026-09-22_mechanical-period-name",
        "old_value": "1500 - 500 BC",
        "new_value": "500 BC - 1 AD",
        "evidence": [
            {"source": "pipeline/utils/text.py:categorize_period", "quote": "(-500)"},
            {"source": f"remediation_change_log:{cites}", "quote": LEFT_BEHIND},
        ],
    }
    base.update(over)
    return base


LABELS = [label_row(30335, TRUNDLE, 29246)]


def build(
    rows: list[dict[str, Any]] = ROWS,
    journal: dict[str, list[dict[str, Any]]] = JOURNAL,
    labels: list[dict[str, Any]] = LABELS,
) -> O.Built:
    return O.build_list(rows, journal, labels, source_sha256="f" * 64)


class TestTheList:
    def test_every_audit_row_is_undone_by_its_journal_row_on_its_deciding_quotes(self) -> None:
        got = build()
        by_id = {e["journal_id"]: e for e in got.reasons["reversals"]}
        assert by_id[28200] == {
            "journal_id": 28200,
            "site_id": MARAY,
            "name": "Marayniyoq",
            "column": "site_type",
            "reason": ROWS[0]["reason"],
            "quotes": [
                {"source": f"opus:{TYPE_KEY}", "text": "Marayniyoq one"},
                {"source": f"opus:{TYPE_KEY}", "text": "Marayniyoq two"},
            ],
            "residual": ROWS[0]["residual"],
        }
        assert [e["journal_id"] for e in got.reasons["reversals"]] == sorted(by_id)
        assert got.ids == (28200, 29001, 29246, 30335)
        assert got.reasons["source"] == {
            "file": "output/remediation/opus_audit/REVERSAL_3_INPUT.jsonl",
            "sha256": "f" * 64,
            "rows": 3,
        }
        assert "journal-reversal-3" in got.reasons["_about"]

    def test_a_start_that_changes_bucket_takes_the_label_the_period_name_lane_derived(
        self,
    ) -> None:
        got = build()
        label = next(e for e in got.reasons["reversals"] if e["column"] == "period_name")
        assert (label["journal_id"], label["site_id"], label["name"]) == (
            30335,
            TRUNDLE,
            "The Trundle",
        )
        assert label["quotes"] == [{"source": "journal", "text": LEFT_BEHIND}]
        assert "29246" in label["reason"] and "'1500 - 500 BC'" in label["reason"]
        assert got.unlabelled == ()

    def test_a_start_within_its_bucket_takes_no_label(self) -> None:
        """Dolni Glavanak's -800 -> -1500 stays in '1500 - 500 BC': a label row citing it is left."""
        got = build(labels=[*LABELS, label_row(30400, DOLNI, 29001)])
        assert 30400 not in got.ids

    def test_only_the_label_row_that_cites_the_start_s_own_write_is_taken(self) -> None:
        other = label_row(30336, TRUNDLE, 27000)
        got = build(labels=[other])
        assert 30336 not in got.ids
        assert got.unlabelled == ("The Trundle",)

    def test_a_label_row_of_another_site_is_never_taken(self) -> None:
        stray = label_row(30337, DOLNI, 29246)
        got = build(labels=[stray])
        assert 30337 not in got.ids and got.unlabelled == ("The Trundle",)

    def test_two_label_rows_citing_one_start_are_refused(self) -> None:
        with pytest.raises(P.PlanError, match="two label rows"):
            build(labels=[*LABELS, label_row(30999, TRUNDLE, 29246)])

    @pytest.mark.parametrize("found", [[], [journal_row(28200, ROWS[0])] * 2])
    def test_a_change_key_that_is_not_exactly_one_journal_row_is_refused(
        self, found: list[dict[str, Any]]
    ) -> None:
        with pytest.raises(P.PlanError, match=r"journal row\(s\)"):
            build(journal={**JOURNAL, TYPE_KEY: found})

    @pytest.mark.parametrize(
        "over",
        [
            {"table_name": "card_stats"},
            {"column_name": "period_start"},
            {"row_pk": TRUNDLE},
            {"old_value": "Settlement"},
            {"new_value": "Temple"},
        ],
    )
    def test_a_journal_row_that_is_not_the_write_the_audit_judged_is_refused(
        self, over: dict[str, Any]
    ) -> None:
        with pytest.raises(P.PlanError, match="the Opus input names"):
            build(journal={**JOURNAL, TYPE_KEY: [journal_row(28200, ROWS[0], **over)]})

    def test_a_journal_row_named_twice_is_refused(self) -> None:
        with pytest.raises(P.PlanError, match="twice"):
            build(journal={**JOURNAL, SAME_KEY: [journal_row(28200, ROWS[2])]})


class Production:
    """Answers the two statements the readers send, and refuses any other."""

    def __init__(self) -> None:
        self.sent: list[str] = []

    def __call__(self, sql: str) -> list[dict[str, Any]]:
        self.sent.append(sql)
        if sql.startswith("SELECT id, change_key, table_name"):
            assert f"change_key IN ('{TYPE_KEY}', '{START_KEY}', '{SAME_KEY}')" in sql
            return [rows[0] for rows in JOURNAL.values()]
        if sql.startswith("SELECT id, row_pk, run_stamp"):
            assert "column_name = 'period_name'" in sql and f"row_pk IN ('{TRUNDLE}')" in sql
            assert sql.endswith("ORDER BY id")
            return LABELS
        raise AssertionError(f"unexpected statement: {sql[:80]!r}")


def test_the_readers_ask_for_exactly_the_rows_they_need() -> None:
    production = Production()
    journal = O.read_journal(production, [r["change_key"] for r in ROWS])
    assert journal == JOURNAL
    assert O.read_labels(production, [TRUNDLE]) == LABELS
    assert len(production.sent) == 2


def test_no_start_that_changes_bucket_reads_no_label() -> None:
    assert O.read_labels(Production(), []) == []


def test_a_change_key_that_is_not_a_phase_3_key_is_never_sent() -> None:
    with pytest.raises(P.PlanError, match="not a phase-3 change key"):
        O.read_journal(Production(), ["phase3:x' OR true --"])


def test_the_starts_that_change_bucket_are_the_ones_whose_label_is_read() -> None:
    assert O.bucket_changes(ROWS) == [ROWS[1]]


def test_the_list_module_is_generated_code_that_holds_exactly_the_ids() -> None:
    text = O.render_list_module((28200, 29001, 29246, 30335), "f" * 64)
    tree = ast.parse(text)
    namespace: dict[str, Any] = {}
    exec(compile(tree, "reversal_3_list.py", "exec"), namespace)  # noqa: S102 - generated here
    assert namespace["JOURNAL_IDS"] == (28200, 29001, 29246, 30335)
    assert "f" * 64 in text and "do not edit by hand" in text
    assert all(len(row) <= 100 for row in text.splitlines())


def test_write_builds_the_reasons_and_the_list_from_the_input(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "REVERSAL_3_INPUT.jsonl"
    source.write_text("".join(json.dumps(r) + "\n" for r in ROWS), encoding="utf-8")
    monkeypatch.setattr(O, "psql_json_reader", Production)
    module = tmp_path / "reversal_3_list.py"
    argv = ["--write", "--input", str(source), "--out", str(tmp_path), "--module", str(module)]
    assert O.main(argv) == 0
    reasons = json.loads((tmp_path / "REASONS.json").read_text(encoding="utf-8"))
    assert reasons["source"]["sha256"] == hashlib.sha256(source.read_bytes()).hexdigest()
    loaded = R.load_reasons(tmp_path / "REASONS.json", L.REVERSAL_3, (28200, 29001, 29246, 30335))
    assert {r.column for r in loaded} == {"site_type", "period_start", "period_name"}
    assert "(28200, 29001, 29246, 30335)" not in module.read_text(encoding="utf-8")
    assert "28200, 29001, 29246, 30335," in module.read_text(encoding="utf-8")


# ------------------------------------------------------------------------- the delivered list
def test_the_delivered_list_is_the_lane_s_and_every_audit_row_is_on_it() -> None:
    """Whatever round the input was regenerated after: the reasons and the code name the same rows,
    every reversal-input row is on it once, quoting its deciding verdicts, and every other row is the
    period label of one of its starts, quoting that label's own journal evidence."""
    directory = A.lane_dir(L.REVERSAL_3)
    reasons = R.load_reasons(
        directory / "REASONS.json", L.REVERSAL_3, L.REVERSAL_LISTS[L.REVERSAL_3.name]
    )
    raw = json.loads((directory / "REASONS.json").read_text(encoding="utf-8"))
    source = REPO / raw["source"]["file"]
    assert raw["source"]["sha256"] == hashlib.sha256(source.read_bytes()).hexdigest(), (
        "REASONS.json was built from another REVERSAL_3_INPUT.jsonl: run reversal_opus.py --write"
    )
    rows = [json.loads(x) for x in source.read_text(encoding="utf-8").splitlines()]
    audited = [r for r in reasons if r.column != "period_name"]
    assert sorted((r.site_id, r.column) for r in audited) == sorted(
        (x["site_id"], x["column"]) for x in rows
    )
    by_cell = {(x["site_id"], x["column"]): x for x in rows}
    for r in audited:
        wanted = by_cell[(r.site_id, r.column)]
        assert [(q.source, q.text) for q in r.quotes] == [
            (f"opus:{wanted['change_key']}", q["text"]) for q in wanted["quotes"]
        ]
    starts = {x["site_id"] for x in O.bucket_changes(rows)}
    labels = [r for r in reasons if r not in audited]
    assert all(r.column == "period_name" and r.site_id in starts for r in labels)
    assert all(q.source == "journal" for r in labels for q in r.quotes)


def test_every_delivered_opus_quote_is_one_the_audit_s_deciding_verdicts_carry() -> None:
    """The lane's check, offline: each quote stands in the found quotes of the verdicts that decided
    to revert its row, and each row is a reversal the audit decided (not superseded)."""
    reasons = R.load_reasons(
        A.lane_dir(L.REVERSAL_3) / "REASONS.json",
        L.REVERSAL_3,
        L.REVERSAL_LISTS[L.REVERSAL_3.name],
    )
    opus = R.load_opus(R.OPUS_AUDIT)
    for r in reasons:
        for q in r.quotes:
            if q.source.startswith("opus:"):
                judged = opus[q.source.partition(":")[2]]
                assert judged.reversal and (judged.site_id, judged.column) == (r.site_id, r.column)
                assert q.text in "\n".join(judged.quotes), (r.name, q.text)
